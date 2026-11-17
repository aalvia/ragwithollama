"""Documentos disponibles, estadísticas e indexación."""

from fastapi import APIRouter, Request

from app.schemas.documents import DocumentListResponse, IndexReport, StatsResponse

router = APIRouter()


@router.get("", response_model=DocumentListResponse)
def list_documents(request: Request) -> DocumentListResponse:
    return request.app.state.indexer.list_documents()


@router.get("/stats", response_model=StatsResponse)
def document_stats(request: Request) -> StatsResponse:
    stats = request.app.state.indexer.stats()
    stats.conversation_context = request.app.state.memory.enabled
    return stats


@router.post("/index", response_model=IndexReport)
def index_documents(request: Request, full: bool = False) -> IndexReport:
    """Indexa lo nuevo o lo modificado. Con ?full=true reconstruye todos los vectores."""
    return request.app.state.indexer.index(full=full)
