"""API con servicios sustituidos. No llama a Ollama."""

from fastapi.testclient import TestClient

from app.errors import OllamaUnavailable
from app.main import app
from app.schemas.chat import ChatResponse
from app.schemas.documents import DocumentListResponse, IndexReport, StatsResponse


class FakeRag:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def answer(self, question: str, session_id: str | None = None) -> ChatResponse:
        self.questions.append(question)
        return ChatResponse(
            question=question,
            answer="Respuesta de prueba basada en un fragmento.",
            sources=[],
            related_documents=[],
            processing_seconds=0.01,
            conversation_context=False,
            used_retrieval=True,
        )


class BrokenRag:
    def answer(self, question: str, session_id: str | None = None) -> ChatResponse:
        raise OllamaUnavailable("No hay conexión con Ollama en http://127.0.0.1:11434.")


class FakeIndexer:
    def list_documents(self) -> DocumentListResponse:
        return DocumentListResponse(documents=[], total=0)

    def stats(self) -> StatsResponse:
        return StatsResponse(
            documents=0,
            chunks=0,
            last_indexed_at=None,
            llm_model="qwen2.5:1.5b",
            embedding_model="nomic-embed-text",
            ollama_status="sin conexión",
            conversation_context=False,
        )

    def index(self, full: bool = False) -> IndexReport:
        return IndexReport(added=["calidad_del_agua.md"], chunks_written=4, duration_seconds=0.2)


class FakeOllama:
    llm_model = "qwen2.5:1.5b"
    embedding_model = "nomic-embed-text"

    def ping(self) -> tuple[bool, list[str]]:
        return False, []


class FakeVectors:
    def count(self) -> int:
        raise RuntimeError("chroma caído")


def test_la_pagina_principal_responde():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "AquaRAG" in response.text
    assert "/static/app.js" in response.text


def test_chat_devuelve_la_respuesta_del_servicio():
    with TestClient(app) as client:
        client.app.state.rag = FakeRag()
        response = client.post("/api/chat", json={"question": "¿Qué es el FCR?", "session_id": "s1"})
    assert response.status_code == 200
    body = response.json()
    assert body["question"] == "¿Qué es el FCR?"
    assert body["answer"].startswith("Respuesta de prueba")
    assert "processing_seconds" in body


def test_pregunta_vacia_se_rechaza():
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"question": " "})
    assert response.status_code == 422


def test_ollama_caido_responde_503():
    with TestClient(app) as client:
        client.app.state.rag = BrokenRag()
        response = client.post("/api/chat", json={"question": "¿Qué es el FCR?"})
    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


def test_documentos_stats_e_indexacion():
    with TestClient(app) as client:
        client.app.state.indexer = FakeIndexer()
        client.app.state.memory.enabled = False
        listed = client.get("/api/documents")
        stats = client.get("/api/documents/stats")
        indexed = client.post("/api/documents/index")
    assert listed.status_code == 200
    assert listed.json()["total"] == 0
    assert stats.json()["llm_model"] == "qwen2.5:1.5b"
    assert stats.json()["embedding_model"] == "nomic-embed-text"
    assert indexed.json()["added"] == ["calidad_del_agua.md"]


def test_health_degradado_si_ollama_no_responde():
    with TestClient(app) as client:
        client.app.state.ollama = FakeOllama()
        client.app.state.vectors = FakeVectors()
        client.app.state.memory.enabled = False
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["fastapi"] == "disponible"
    assert body["ollama"] == "sin conexión"
    assert body["llm_available"] is False
    assert body["chromadb"] == "error"


def test_el_frontend_puede_llamar_al_backend():
    """El JavaScript de la página usa las mismas rutas que este cliente."""
    with TestClient(app) as client:
        client.app.state.rag = FakeRag()
        client.app.state.indexer = FakeIndexer()
        client.app.state.memory.enabled = False
        page = client.get("/static/app.js")
        chat = client.post("/api/chat", json={"question": "bioseguridad"})
        stats = client.get("/api/documents/stats")
    script = page.text
    assert page.status_code == 200
    assert "/api/chat" in script
    assert "/api/documents/index" in script
    assert chat.status_code == 200
    assert stats.status_code == 200
