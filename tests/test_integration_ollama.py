"""Pruebas que usan el Ollama local. Se ejecutan aparte de las unitarias."""

from pathlib import Path

import pytest

from app.config import Settings
from app.main import build_services
from app.services.rag_service import INSUFFICIENT_ANSWER

pytestmark = pytest.mark.integration


@pytest.fixture
def services(tmp_path: Path):
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "oxigeno.md").write_text(
        """# Oxígeno disuelto

En un estanque de camarón el oxígeno disuelto suele ser más bajo antes del amanecer,
porque durante la noche los organismos consumen oxígeno y no hay fotosíntesis.
Un valor orientativo de manejo en engorde es mantenerlo por encima de 4 mg/L.
Por debajo de 3 mg/L el camarón puede dejar de comer. Esto depende de la etapa,
la temperatura y la biomasa. No es un límite universal.

# Alimentación

Las bandejas de alimentación permiten ver si el alimento fue consumido.
No se debe aumentar la ración si la bandeja amanece con sobrante.
""",
        encoding="utf-8",
    )
    (documents / "fcr.md").write_text(
        """# Factor de conversión alimenticia

El FCR se calcula así: alimento suministrado en kilogramos dividido entre
la biomasa ganada en kilogramos. Un ejemplo didáctico: 1500 kg de alimento
y 1000 kg de biomasa ganada dan un FCR de 1,5. Es un indicador de eficiencia,
no un diagnóstico. El valor conveniente depende del sistema de cultivo.
""",
        encoding="utf-8",
    )
    settings = Settings(
        chroma_db_path=str(tmp_path / "chroma"),
        documents_path=str(documents),
        index_state_path=str(tmp_path / "index_state.json"),
        conversation_context=False,
        chunk_size=400,
        chunk_overlap=60,
        top_k=3,
        max_distance=0.30,
    )
    built = build_services(settings)
    yield built
    built["ollama"].close()


def test_ollama_tiene_los_modelos_y_genera_un_embedding(services):
    available, names = services["ollama"].ping()
    assert available is True
    joined = " ".join(names)
    assert "qwen2.5:1.5b" in joined
    assert "nomic-embed-text" in joined
    vector = services["rag"]._embeddings.embed_query("oxígeno disuelto en el estanque")
    assert len(vector) > 100
    assert all(isinstance(value, float) for value in vector[:5])


def test_indexa_recupera_fuente_y_rechaza_un_tema_ajeno(services):
    report = services["indexer"].index()
    assert report.errors == []
    assert report.chunks_written >= 2
    assert services["vectors"].count() >= 2

    oxygen = services["rag"].answer("¿Por qué el oxígeno disuelto baja antes del amanecer?")
    assert oxygen.used_retrieval is True
    assert oxygen.sources
    assert any("oxigeno.md" in source.document for source in oxygen.sources)
    assert "oxígeno" in oxygen.answer.lower() or "amanecer" in oxygen.answer.lower()

    fcr = services["rag"].answer("¿Cómo se calcula el factor de conversión alimenticia?")
    assert fcr.used_retrieval is True
    assert any("fcr.md" in source.document for source in fcr.sources)

    unrelated = services["rag"].answer("¿Cuál es la capital de Francia y qué museo tiene la Mona Lisa?")
    assert unrelated.used_retrieval is False
    assert unrelated.sources == []
    assert unrelated.answer == INSUFFICIENT_ANSWER


def test_un_archivo_sin_cambios_no_se_vuelve_a_indexar(services):
    first = services["indexer"].index()
    second = services["indexer"].index()
    assert first.chunks_written >= 2
    assert second.unchanged
    assert second.chunks_written == 0
    assert second.added == []
    assert second.updated == []
