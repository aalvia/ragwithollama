"""Recuperación, memoria de conversación y respuesta con dobles de prueba."""

from app.repositories.vector_repository import StoredChunk
from app.services.conversation_service import ConversationMemory
from app.services.embedding_service import with_prefix
from app.services.indexing_service import plan_index_actions
from app.services.ollama_service import model_installed
from app.services.rag_service import INSUFFICIENT_ANSWER, RagService, build_messages, build_search_text


class FakeOllama:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        return "Según calidad_del_agua.md, el oxígeno se observa al amanecer."


class FakeEmbeddings:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class FakeVectors:
    def __init__(self, hits: list[StoredChunk]) -> None:
        self.hits = hits
        self.top_k = None

    def query(self, embedding: list[float], top_k: int) -> list[StoredChunk]:
        self.top_k = top_k
        return self.hits


def _hit(distance: float, name: str = "oxigeno_disuelto_temperatura.md") -> StoredChunk:
    return StoredChunk(
        chunk_id=f"{name}::c0000",
        text="Documento: ejemplo\n\nEl oxígeno disuelto baja antes del amanecer.",
        source_name=name,
        source_path=name,
        page=None,
        heading="Oxígeno",
        distance=distance,
    )


def test_prefijo_de_nomic_cambia_entre_documento_y_pregunta():
    assert with_prefix("estanque", "document").startswith("search_document: ")
    assert with_prefix("estanque", "query").startswith("search_query: ")
    assert with_prefix("search_query: estanque", "query") == "search_query: estanque"


def test_modelo_latest_coincide_con_el_nombre_corto():
    installed = ["qwen2.5:1.5b", "nomic-embed-text:latest"]
    assert model_installed("qwen2.5:1.5b", installed)
    assert model_installed("nomic-embed-text", installed)
    assert not model_installed("qwen2.5:7b", installed)


def test_busqueda_sin_memoria_usa_solo_la_pregunta():
    assert build_search_text("¿y en postlarvas?", []) == "¿y en postlarvas?"


def test_busqueda_con_memoria_incluye_la_pregunta_anterior():
    history = [{"role": "user", "content": "Háblame del oxígeno disuelto"}, {"role": "assistant", "content": "Se mide al amanecer."}]
    text = build_search_text("¿y en postlarvas?", history)
    assert "oxígeno disuelto" in text
    assert "postlarvas" in text


def test_mensajes_sin_historial_no_arrastran_turnos():
    messages = build_messages("¿Qué es el FCR?", [_hit(0.2, "conversion_alimenticia_fcr.md")], [])
    contents = " ".join(item["content"] for item in messages)
    assert messages[0]["role"] == "system"
    assert "postlarvas" not in contents
    assert "FCR" in contents


def test_sin_fragmentos_relevantes_no_llama_al_modelo():
    ollama = FakeOllama()
    service = RagService(
        ollama=ollama,
        embeddings=FakeEmbeddings(),
        vectors=FakeVectors([_hit(0.92)]),
        memory=ConversationMemory(enabled=False, max_turns=4),
        top_k=5,
        max_distance=0.30,
    )
    response = service.answer("¿Cuál es la capital de Francia?", session_id="s1")
    assert response.answer == INSUFFICIENT_ANSWER
    assert response.sources == []
    assert response.used_retrieval is False
    assert ollama.calls == []


def test_con_fragmentos_devuelve_fuente_y_respuesta():
    ollama = FakeOllama()
    service = RagService(
        ollama=ollama,
        embeddings=FakeEmbeddings(),
        vectors=FakeVectors([_hit(0.21)]),
        memory=ConversationMemory(enabled=False, max_turns=4),
        top_k=3,
        max_distance=0.30,
    )
    response = service.answer("¿Cuándo baja el oxígeno?", session_id="s1")
    assert response.used_retrieval is True
    assert response.sources[0].document == "oxigeno_disuelto_temperatura.md"
    assert response.related_documents == ["oxigeno_disuelto_temperatura.md"]
    assert ollama.calls[0][-1]["role"] == "user"
    assert "Fragmento 1" in ollama.calls[0][-1]["content"]


def test_contexto_apagado_no_guarda_ni_reutiliza_la_pregunta_anterior():
    embeddings = FakeEmbeddings()
    memory = ConversationMemory(enabled=False, max_turns=4)
    service = RagService(
        ollama=FakeOllama(),
        embeddings=embeddings,
        vectors=FakeVectors([_hit(0.2)]),
        memory=memory,
        top_k=5,
        max_distance=0.30,
    )
    service.answer("Háblame del oxígeno disuelto", session_id="abc")
    service.answer("¿y en postlarvas?", session_id="abc")
    assert embeddings.queries[1] == "¿y en postlarvas?"
    assert memory.history("abc") == []


def test_contexto_encendido_guarda_el_turno_y_amplia_la_busqueda():
    embeddings = FakeEmbeddings()
    ollama = FakeOllama()
    memory = ConversationMemory(enabled=True, max_turns=2)
    service = RagService(
        ollama=ollama,
        embeddings=embeddings,
        vectors=FakeVectors([_hit(0.2)]),
        memory=memory,
        top_k=5,
        max_distance=0.30,
    )
    service.answer("Háblame del oxígeno disuelto", session_id="abc")
    service.answer("¿y en postlarvas?", session_id="abc")
    assert "oxígeno disuelto" in embeddings.queries[1]
    roles = [item["role"] for item in ollama.calls[1]]
    assert roles.count("user") == 2
    assert len(memory.history("abc")) == 4

    service.answer("¿y la temperatura?", session_id="abc")
    assert len(memory.history("abc")) == 4


def test_plan_de_indexacion_esta_cubierto_aqui_tambien():
    actions = plan_index_actions({"a.md": "1"}, {})
    assert actions["added"] == ["a.md"]
