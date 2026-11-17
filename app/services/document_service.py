"""Lectura de documentos, limpieza y división en fragmentos."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import fitz
from docx import Document
from openpyxl import load_workbook

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx", ".xlsx"}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


@dataclass(frozen=True)
class FoundFile:
    path: Path
    relative_path: str
    name: str
    extension: str
    size_bytes: int
    content_hash: str


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    page: int | None
    heading: str
    index: int
    source_name: str
    source_path: str


class DocumentService:
    """Recorre la carpeta de conocimiento y prepara fragmentos para indexar."""

    def __init__(self, documents_path: Path, chunk_size: int, chunk_overlap: int) -> None:
        self.documents_path = documents_path
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def list_files(self) -> list[FoundFile]:
        if not self.documents_path.exists():
            return []
        found: list[FoundFile] = []
        for path in sorted(self.documents_path.rglob("*")):
            if not path.is_file():
                continue
            if path.name.startswith((".", "~$")):
                continue
            extension = path.suffix.lower()
            if extension not in SUPPORTED_EXTENSIONS:
                continue
            relative = path.resolve().relative_to(self.documents_path.resolve()).as_posix()
            found.append(
                FoundFile(
                    path=path,
                    relative_path=relative,
                    name=path.name,
                    extension=extension,
                    size_bytes=path.stat().st_size,
                    content_hash=file_hash(path),
                )
            )
        return found

    def build_chunks(self, document: FoundFile) -> list[Chunk]:
        blocks = extract_blocks(document.path, document.extension)
        chunks: list[Chunk] = []
        for heading, page, text in blocks:
            pieces = split_text(clean_text(text), self.chunk_size, self.chunk_overlap)
            for piece in pieces:
                stored = compose_chunk_text(document.name, heading, piece)
                chunks.append(
                    Chunk(
                        chunk_id=f"{document.relative_path}::c{len(chunks):04d}",
                        text=stored,
                        page=page,
                        heading=heading or "",
                        index=len(chunks),
                        source_name=document.name,
                        source_path=document.relative_path,
                    )
                )
        return chunks


def file_hash(path: Path) -> str:
    """Hash del archivo en disco. Si el archivo cambia, el hash cambia y se reindexa."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    """Quita caracteres de control y espacios vacíos repetidos."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = CONTROL_CHARACTERS.sub(" ", normalized)
    lines = [line.strip() for line in normalized.split("\n")]
    compact = "\n".join(lines)
    while "\n\n\n" in compact:
        compact = compact.replace("\n\n\n", "\n\n")
    return compact.strip()


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """Parte un texto en fragmentos, procurando cortar en un párrafo o una frase."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            window = text[start:end]
            break_at = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
            if break_at >= size // 2:
                end = start + break_at + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start
    return chunks


def split_markdown_sections(text: str) -> list[tuple[str | None, str]]:
    """Separa un Markdown por títulos para que cada fragmento conserve su sección."""
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            body = "\n".join(buffer).strip()
            if body:
                sections.append((heading, body))
            heading = line.lstrip("#").strip()
            buffer = []
        else:
            buffer.append(line)
    body = "\n".join(buffer).strip()
    if body:
        sections.append((heading, body))
    if sections:
        return sections
    stripped = text.strip()
    return [(None, stripped)] if stripped else []


def compose_chunk_text(document_name: str, heading: str | None, body: str) -> str:
    """Incluye archivo y sección dentro del texto que se va a vectorizar y a mostrar."""
    lines = [f"Documento: {document_name}"]
    if heading:
        lines.append(f"Sección: {heading}")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


def extract_blocks(path: Path, extension: str) -> list[tuple[str | None, int | None, str]]:
    """Devuelve tuplas (sección, página, texto). La página solo existe en PDF."""
    if extension in {".md", ".txt"}:
        raw = read_text_file(path)
        if extension == ".md":
            return [(heading, None, body) for heading, body in split_markdown_sections(raw)]
        return [(None, None, raw)]
    if extension == ".pdf":
        return _extract_pdf(path)
    if extension == ".docx":
        return [(None, None, _extract_docx(path))]
    if extension == ".xlsx":
        return [(None, None, _extract_xlsx(path))]
    logger.warning("Extensión no soportada: %s", path)
    return []


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_pdf(path: Path) -> list[tuple[str | None, int | None, str]]:
    blocks: list[tuple[str | None, int | None, str]] = []
    with fitz.open(path) as document:
        for number, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            if text.strip():
                blocks.append((None, number, text))
    return blocks


def _extract_docx(path: Path) -> str:
    document = Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_xlsx(path: Path) -> str:
    workbook = load_workbook(path, read_only=True, data_only=True)
    lines: list[str] = []
    try:
        for sheet in workbook.worksheets:
            lines.append(f"Hoja: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                values = ["" if cell is None else str(cell).strip() for cell in row]
                if any(values):
                    lines.append(" | ".join(values))
    finally:
        workbook.close()
    return "\n".join(lines)
