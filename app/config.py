"""Configuración central. Los valores salen de .env o de las variables de entorno."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Parámetros operativos de AquaRAG."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"
    ollama_embedding_model: str = "nomic-embed-text"
    ollama_timeout_seconds: float = 180
    ollama_temperature: float = 0.1
    ollama_max_tokens: int = 700

    chroma_db_path: str = "./data/chroma_db"
    documents_path: str = "./data/documents"
    index_state_path: str = "./data/index_state.json"

    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = Field(default=5, ge=1, le=20)
    max_distance: float = Field(default=0.30, ge=0.0, le=2.0)

    conversation_context: bool = False
    conversation_max_turns: int = Field(default=4, ge=1, le=20)

    host: str = "127.0.0.1"
    port: int = 8000

    @field_validator("ollama_base_url")
    @classmethod
    def strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("chunk_overlap")
    @classmethod
    def overlap_smaller_than_chunk(cls, value: int, info) -> int:
        chunk_size = info.data.get("chunk_size", 800)
        if value < 0:
            raise ValueError("CHUNK_OVERLAP no puede ser negativo")
        if value >= chunk_size:
            raise ValueError("CHUNK_OVERLAP debe ser menor que CHUNK_SIZE")
        return value

    def path(self, value: str) -> Path:
        """Resuelve una ruta relativa contra la raíz del proyecto, no contra el directorio actual."""
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = ROOT_DIR / candidate
        return candidate.resolve()

    @property
    def chroma_path(self) -> Path:
        return self.path(self.chroma_db_path)

    @property
    def documents_dir(self) -> Path:
        return self.path(self.documents_path)

    @property
    def index_state_file(self) -> Path:
        return self.path(self.index_state_path)


@lru_cache
def get_settings() -> Settings:
    """Devuelve una sola instancia para que toda la aplicación lea la misma configuración."""
    return Settings()
