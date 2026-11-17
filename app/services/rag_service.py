"""Recuperación semántica y redacción con el modelo local."""

from __future__ import annotations

import logging
import time

from app.repositories.vector_repository import StoredChunk, VectorRepository
from app.schemas.chat import ChatResponse, SourceItem
from app.services.conversation_service import ConversationMemory
from app.services.embedding_service import EmbeddingService
from app.services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres AquaRAG, un asistente de conocimiento sobre acuicultura de camarón blanco del Pacífico (Litopenaeus vannamei), con atención al contexto de cultivo en Ecuador.

Reglas de respuesta:
- Responde en español, con frases claras y concretas.
- Usa exclusivamente los fragmentos recuperados para cifras, procedimientos, rangos e indicadores.
- Si un dato no aparece en los fragmentos, dilo. No lo completes con conocimiento externo.
- No inventes estudios, autores, normativas ni resultados de una camaronera real.
- Distingue lo que el fragmento afirma de cualquier lectura adicional. Si infieres algo, márcalo como lectura del texto y no como un hecho medido.
- Cuando uses un dato, menciona el nombre del archivo de origen.
- Recuerda que los valores de los documentos son orientativos y dependen de la especie, la etapa, la zona y el manejo.
- No des un diagnóstico sanitario ni una dosis. Si la pregunta es de enfermedad, indica que hace falta confirmación profesional.
- No afirmes haber consultado documentos que no estén en los fragmentos de este mensaje.
"""

INSUFFICIENT_ANSWER = (
    "No encuentro información suficiente en la base documental para responder con respaldo. "
    "Puedes reformular la pregunta o agregar un documento sobre el tema y volver a indexar. "
    "No voy a completar la respuesta con datos que no estén en los fragmentos recuperados."
)

EXCERPT_LIMIT = 500
HISTORY_LIMIT = 700


class RagService:
    """Une la pregunta, los fragmentos cercanos y la respuesta del modelo."""

    def __init__(
        self,
        ollama: OllamaService,
        embeddings: EmbeddingService,
        vectors: VectorRepository,
        memory: ConversationMemory,
        top_k: int,
        max_distance: float,
    ) -> None:
        self._ollama = ollama
        self._embeddings = embeddings
        self._vectors = vectors
        self._memory = memory
        self._top_k = top_k
        self._max_distance = max_distance

    def answer(self, question: str, session_id: str | None = None) -> ChatResponse:
        started = time.perf_counter()
        history = self._memory.history(session_id)
        query_text = build_search_text(question, history)
        embedding = self._embeddings.embed_query(query_text)
        retrieved = self._vectors.query(embedding, self._top_k)
        relevant = [hit for hit in retrieved if hit.distance <= self._max_distance]
        best = min((hit.distance for hit in retrieved), default=None)
        logger.info(
            "Recuperación: %s candidatos, %s dentro del umbral %.2f. Mejor distancia=%s",
            len(retrieved),
            len(relevant),
            self._max_distance,
            None if best is None else round(best, 3),
        )

        if not relevant:
            answer = INSUFFICIENT_ANSWER
            sources: list[SourceItem] = []
            used_retrieval = False
        else:
            answer = self._ollama.chat(build_messages(question, relevant, history))
            sources = [to_source(hit) for hit in relevant]
            used_retrieval = True

        self._memory.remember(session_id, question, answer)
        related = list(dict.fromkeys(source.document for source in sources))
        return ChatResponse(
            question=question,
            answer=answer,
            sources=sources,
            related_documents=related,
            processing_seconds=round(time.perf_counter() - started, 3),
            conversation_context=self._memory.enabled,
            used_retrieval=used_retrieval,
        )


def build_search_text(question: str, history: list[dict[str, str]]) -> str:
    """Si hay memoria, la búsqueda incluye la pregunta anterior para entender un seguimiento."""
    previous = [item["content"] for item in history if item["role"] == "user"]
    if not previous:
        return question.strip()
    return f"{previous[-1].strip()}\n{question.strip()}"


def build_messages(
    question: str,
    chunks: list[StoredChunk],
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Hay turnos previos de esta sesión. Úsalos solo para entender a qué se refiere "
                    "una pregunta corta. Las cifras y los procedimientos siguen saliendo de los fragmentos."
                ),
            }
        )
        for item in history:
            messages.append(
                {
                    "role": item["role"],
                    "content": _clip(item["content"], HISTORY_LIMIT),
                }
            )
    messages.append({"role": "user", "content": build_user_prompt(question, chunks)})
    return messages


def build_user_prompt(question: str, chunks: list[StoredChunk]) -> str:
    blocks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        page = f"página {chunk.page}" if chunk.page else "sin página"
        blocks.append(f"[Fragmento {index} | {chunk.source_name} | {page}]\n{chunk.text}")
    context = "\n\n".join(blocks)
    return (
        "Responde la pregunta usando exclusivamente los fragmentos siguientes.\n\n"
        f"{context}\n\n"
        f"Pregunta: {question.strip()}"
    )


def to_source(hit: StoredChunk) -> SourceItem:
    return SourceItem(
        document=hit.source_name,
        path=hit.source_path,
        page=hit.page,
        chunk_id=hit.chunk_id,
        heading=hit.heading,
        excerpt=_clip(hit.text, EXCERPT_LIMIT),
        distance=round(hit.distance, 4),
    )


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
