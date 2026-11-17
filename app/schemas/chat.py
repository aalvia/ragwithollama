"""Contratos del endpoint de conversación."""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    session_id: str | None = Field(default=None, max_length=80)


class SourceItem(BaseModel):
    document: str
    path: str
    page: int | None = None
    chunk_id: str
    heading: str = ""
    excerpt: str
    distance: float


class ChatResponse(BaseModel):
    question: str
    answer: str
    sources: list[SourceItem]
    related_documents: list[str]
    processing_seconds: float
    conversation_context: bool
    used_retrieval: bool
