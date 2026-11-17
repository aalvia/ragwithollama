"""ChromaDB persistente. Guarda vectores ya calculados por Ollama; no descarga un modelo propio."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

import chromadb

logger = logging.getLogger(__name__)


def _collection_names(client) -> set[str]:
    """Chroma 1.x devuelve nombres; versiones anteriores devolvían objetos con .name."""
    names: set[str] = set()
    for item in client.list_collections():
        names.add(item if isinstance(item, str) else item.name)
    return names

COLLECTION_NAME = "aquarag"


@dataclass(frozen=True)
class StoredChunk:
    chunk_id: str
    text: str
    source_name: str
    source_path: str
    page: int | None
    heading: str
    distance: float


class VectorRepository:
    """Almacén vectorial local. Una colección, un modelo de embeddings, disco en data/chroma_db."""

    def __init__(self, persist_path: Path, embedding_model: str) -> None:
        persist_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_path))
        self.embedding_model = embedding_model
        self._collection = self._open_collection()

    def _open_collection(self):
        existing = _collection_names(self._client)
        if COLLECTION_NAME in existing:
            collection = self._client.get_collection(COLLECTION_NAME)
            stored_model = (collection.metadata or {}).get("embedding_model")
            if stored_model and stored_model != self.embedding_model:
                raise RuntimeError(
                    "La base vectorial fue creada con el modelo "
                    f"'{stored_model}' y ahora está configurado '{self.embedding_model}'. "
                    "Borra la carpeta data/chroma_db y vuelve a indexar."
                )
            return collection
        return self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "embedding_model": self.embedding_model},
        )

    def count(self) -> int:
        return int(self._collection.count())

    def replace_document(
        self,
        source_path: str,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        """Sustituye todos los fragmentos de un archivo. Si el archivo no tenía fragmentos, solo inserta."""
        self.delete_document(source_path)
        if not ids:
            return
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete_document(self, source_path: str) -> None:
        existing = self._collection.get(where={"source_path": source_path})
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)

    def query(self, embedding: list[float], top_k: int) -> list[StoredChunk]:
        total = self.count()
        if total == 0:
            return []
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, total),
            include=["documents", "metadatas", "distances"],
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        hits: list[StoredChunk] = []
        for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
            metadata = metadata or {}
            page_value = metadata.get("page", -1)
            page = int(page_value) if isinstance(page_value, int) and page_value > 0 else None
            hits.append(
                StoredChunk(
                    chunk_id=str(chunk_id),
                    text=str(text or ""),
                    source_name=str(metadata.get("source_name") or ""),
                    source_path=str(metadata.get("source_path") or ""),
                    page=page,
                    heading=str(metadata.get("heading") or ""),
                    distance=float(distance),
                )
            )
        return hits
