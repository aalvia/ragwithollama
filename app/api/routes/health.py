"""Estado de FastAPI, Ollama, los modelos y ChromaDB."""

from fastapi import APIRouter, Request

from app.schemas.documents import HealthResponse
from app.services.ollama_service import model_installed

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    ollama = request.app.state.ollama
    vectors = request.app.state.vectors
    available, names = ollama.ping()
    try:
        chunks = vectors.count()
        chroma_status = "disponible"
    except Exception:
        chunks = 0
        chroma_status = "error"
    llm_ok = available and model_installed(ollama.llm_model, names)
    embed_ok = available and model_installed(ollama.embedding_model, names)
    overall = "ok" if available and llm_ok and embed_ok and chroma_status == "disponible" else "degraded"
    if not available:
        ollama_status = "sin conexión"
    else:
        ollama_status = "disponible"
    return HealthResponse(
        status=overall,
        fastapi="disponible",
        ollama=ollama_status,
        llm_model=ollama.llm_model,
        llm_available=llm_ok,
        embedding_model=ollama.embedding_model,
        embedding_available=embed_ok,
        chromadb=chroma_status,
        chunks=chunks,
        conversation_context=request.app.state.memory.enabled,
    )
