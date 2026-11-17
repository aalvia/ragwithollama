"""Prefijos y llamadas de embeddings. nomic-embed-text exige un prefijo distinto para documentos y preguntas."""

from app.services.ollama_service import OllamaService

DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "


def with_prefix(text: str, purpose: str) -> str:
    """Aplica el prefijo que el modelo de embeddings usa para buscar."""
    prefix = DOCUMENT_PREFIX if purpose == "document" else QUERY_PREFIX
    stripped = text.strip()
    if stripped.startswith(prefix):
        return stripped
    return prefix + stripped


class EmbeddingService:
    """Convierte textos en vectores usando el modelo de embeddings de Ollama."""

    def __init__(self, ollama: OllamaService) -> None:
        self._ollama = ollama

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._ollama.embed([with_prefix(text, "document") for text in texts])

    def embed_query(self, text: str) -> list[float]:
        vectors = self._ollama.embed([with_prefix(text, "query")])
        return vectors[0]
