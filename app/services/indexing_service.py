"""Indexación incremental: solo toca archivos nuevos, modificados o eliminados."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.errors import OllamaUnavailable
from app.repositories.vector_repository import VectorRepository
from app.schemas.documents import DocumentItem, DocumentListResponse, IndexReport, StatsResponse
from app.services.document_service import DocumentService, FoundFile
from app.services.embedding_service import EmbeddingService
from app.services.ollama_service import OllamaService

logger = logging.getLogger(__name__)


def plan_index_actions(
    found_hashes: dict[str, str],
    indexed_hashes: dict[str, str],
) -> dict[str, list[str]]:
    """Compara hashes del disco con los ya indexados. Función pura, fácil de probar."""
    found = set(found_hashes)
    indexed = set(indexed_hashes)
    added = sorted(found - indexed)
    removed = sorted(indexed - found)
    updated = sorted(
        path for path in found & indexed if found_hashes[path] != indexed_hashes[path]
    )
    unchanged = sorted(
        path for path in found & indexed if found_hashes[path] == indexed_hashes[path]
    )
    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "unchanged": unchanged,
    }


class IndexingService:
    """Coordina lectura, embeddings y ChromaDB."""

    def __init__(
        self,
        documents: DocumentService,
        embeddings: EmbeddingService,
        vectors: VectorRepository,
        ollama: OllamaService,
        ledger_path: Path,
    ) -> None:
        self._documents = documents
        self._embeddings = embeddings
        self._vectors = vectors
        self._ollama = ollama
        self._ledger_path = ledger_path

    def index(self, full: bool = False) -> IndexReport:
        started = time.perf_counter()
        files = self._documents.list_files()
        by_path = {item.relative_path: item for item in files}
        ledger = self._load_ledger()
        original_hashes = {
            path: str(meta.get("content_hash", ""))
            for path, meta in ledger.get("files", {}).items()
        }
        force = full or self._vectors.count() == 0
        actions = plan_index_actions(
            {path: item.content_hash for path, item in by_path.items()},
            {} if force else original_hashes,
        )
        if force:
            present = set(by_path)
            previously = set(original_hashes)
            actions["removed"] = sorted(previously - present)
            actions["updated"] = sorted(set(actions["added"]) & previously)
            actions["added"] = sorted(set(actions["added"]) - previously)
            actions["unchanged"] = []
        report = IndexReport(
            added=actions["added"],
            updated=actions["updated"],
            removed=actions["removed"],
            unchanged=actions["unchanged"],
        )
        logger.info(
            "Indexación: %s nuevos, %s modificados, %s eliminados, %s sin cambios",
            len(report.added),
            len(report.updated),
            len(report.removed),
            len(report.unchanged),
        )

        for relative_path in report.removed:
            self._vectors.delete_document(relative_path)
            ledger["files"].pop(relative_path, None)

        try:
            for relative_path in report.added + report.updated:
                document = by_path[relative_path]
                try:
                    written = self._index_file(document)
                except OllamaUnavailable:
                    raise
                except Exception as exc:
                    message = f"{relative_path}: {exc}"
                    logger.exception("No se pudo indexar %s", relative_path)
                    report.errors.append(message)
                    continue
                report.chunks_written += written
                ledger["files"][relative_path] = {
                    "content_hash": document.content_hash,
                    "chunks": written,
                    "indexed_at": _now(),
                }
        finally:
            ledger["last_indexed_at"] = _now()
            self._save_ledger(ledger)

        report.duration_seconds = round(time.perf_counter() - started, 3)
        return report

    def list_documents(self) -> DocumentListResponse:
        ledger = self._load_ledger()
        indexed = ledger.get("files", {})
        items: list[DocumentItem] = []
        for document in self._documents.list_files():
            previous = indexed.get(document.relative_path)
            if previous is None:
                status = "pending"
            elif previous.get("content_hash") != document.content_hash:
                status = "modified"
            else:
                status = "indexed"
            items.append(
                DocumentItem(
                    name=document.name,
                    relative_path=document.relative_path,
                    extension=document.extension,
                    size_bytes=document.size_bytes,
                    status=status,
                )
            )
        return DocumentListResponse(documents=items, total=len(items))

    def stats(self) -> StatsResponse:
        ledger = self._load_ledger()
        available, _names = self._ollama.ping()
        return StatsResponse(
            documents=len(self._documents.list_files()),
            chunks=self._vectors.count(),
            last_indexed_at=ledger.get("last_indexed_at"),
            llm_model=self._ollama.llm_model,
            embedding_model=self._ollama.embedding_model,
            ollama_status="disponible" if available else "sin conexión",
            conversation_context=False,
        )

    def _index_file(self, document: FoundFile) -> int:
        chunks = self._documents.build_chunks(document)
        if not chunks:
            logger.warning("Sin texto útil en %s", document.relative_path)
            self._vectors.delete_document(document.relative_path)
            return 0
        vectors = self._embeddings.embed_documents([chunk.text for chunk in chunks])
        indexed_at = _now()
        self._vectors.replace_document(
            source_path=document.relative_path,
            ids=[chunk.chunk_id for chunk in chunks],
            embeddings=vectors,
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "source_name": chunk.source_name,
                    "source_path": chunk.source_path,
                    "page": chunk.page if chunk.page is not None else -1,
                    "chunk_index": chunk.index,
                    "heading": chunk.heading,
                    "indexed_at": indexed_at,
                    "content_hash": document.content_hash,
                }
                for chunk in chunks
            ],
        )
        logger.info("Indexado %s en %s fragmentos", document.relative_path, len(chunks))
        return len(chunks)

    def _load_ledger(self) -> dict:
        if not self._ledger_path.exists():
            return {"last_indexed_at": None, "files": {}}
        try:
            data = json.loads(self._ledger_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("El registro de indexación estaba dañado. Se reconstruirá.")
            return {"last_indexed_at": None, "files": {}}
        data.setdefault("files", {})
        return data

    def _save_ledger(self, ledger: dict) -> None:
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self._ledger_path.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
