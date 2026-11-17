"""Contratos de documentos, indexación y estado del sistema."""

from typing import Literal

from pydantic import BaseModel, Field


class DocumentItem(BaseModel):
    name: str
    relative_path: str
    extension: str
    size_bytes: int
    status: Literal["indexed", "modified", "pending"]


class DocumentListResponse(BaseModel):
    documents: list[DocumentItem]
    total: int


class IndexReport(BaseModel):
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    unchanged: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    chunks_written: int = 0
    duration_seconds: float = 0


class StatsResponse(BaseModel):
    documents: int
    chunks: int
    last_indexed_at: str | None
    llm_model: str
    embedding_model: str
    ollama_status: str
    conversation_context: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    fastapi: str
    ollama: str
    llm_model: str
    llm_available: bool
    embedding_model: str
    embedding_available: bool
    chromadb: str
    chunks: int
    conversation_context: bool
