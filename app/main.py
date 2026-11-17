"""Aplicación FastAPI. Sirve la API y la página web en el mismo proceso."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import chat, documents, health
from app.config import Settings, get_settings
from app.errors import AquaRAGError
from app.repositories.vector_repository import VectorRepository
from app.services.conversation_service import ConversationMemory
from app.services.document_service import DocumentService
from app.services.embedding_service import EmbeddingService
from app.services.indexing_service import IndexingService
from app.services.ollama_service import OllamaService
from app.services.rag_service import RagService

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
logger = logging.getLogger("aquarag")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)


def build_services(settings: Settings) -> dict:
    """Arma los objetos de la aplicación. Los tests pueden llamar esto con rutas temporales."""
    settings.documents_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)
    ollama = OllamaService(
        base_url=settings.ollama_base_url,
        llm_model=settings.ollama_model,
        embedding_model=settings.ollama_embedding_model,
        timeout_seconds=settings.ollama_timeout_seconds,
        temperature=settings.ollama_temperature,
        max_tokens=settings.ollama_max_tokens,
    )
    embeddings = EmbeddingService(ollama)
    document_service = DocumentService(
        documents_path=settings.documents_dir,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    vectors = VectorRepository(settings.chroma_path, settings.ollama_embedding_model)
    indexer = IndexingService(
        documents=document_service,
        embeddings=embeddings,
        vectors=vectors,
        ollama=ollama,
        ledger_path=settings.index_state_file,
    )
    memory = ConversationMemory(
        enabled=settings.conversation_context,
        max_turns=settings.conversation_max_turns,
    )
    rag = RagService(
        ollama=ollama,
        embeddings=embeddings,
        vectors=vectors,
        memory=memory,
        top_k=settings.top_k,
        max_distance=settings.max_distance,
    )
    return {
        "settings": settings,
        "ollama": ollama,
        "documents": document_service,
        "vectors": vectors,
        "indexer": indexer,
        "memory": memory,
        "rag": rag,
    }


def create_app() -> FastAPI:
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = build_services(get_settings())
        for name, service in services.items():
            setattr(app.state, name, service)
        logger.info(
            "AquaRAG listo. LLM=%s embeddings=%s contexto=%s",
            services["ollama"].llm_model,
            services["ollama"].embedding_model,
            services["memory"].enabled,
        )
        try:
            yield
        finally:
            services["ollama"].close()

    app = FastAPI(
        title="AquaRAG",
        description="Asistente RAG local para la industria camaronera.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(chat.router, prefix="/api")
    app.include_router(documents.router, prefix="/api/documents")
    app.include_router(health.router, prefix="/api")

    @app.exception_handler(AquaRAGError)
    async def handle_application_error(_request: Request, exc: AquaRAGError) -> JSONResponse:
        logger.warning("Error de aplicación: %s", exc.message)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado")
        return JSONResponse(
            status_code=500,
            content={"detail": "Ocurrió un error interno. El detalle quedó en el log del servidor."},
        )

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    return app


app = create_app()
