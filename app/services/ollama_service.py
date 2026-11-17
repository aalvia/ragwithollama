"""Cliente HTTP de Ollama. No usa APIs de pago: solo el servidor local."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.errors import OllamaUnavailable

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 16


class OllamaService:
    """Habla con el Ollama que ya está instalado en la máquina."""

    def __init__(
        self,
        base_url: str,
        llm_model: str,
        embedding_model: str,
        timeout_seconds: float,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.llm_model = llm_model
        self.embedding_model = embedding_model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._timeout = httpx.Timeout(connect=5.0, read=timeout_seconds, write=60.0, pool=5.0)
        self._client = httpx.Client(base_url=self.base_url, timeout=self._timeout)

    def close(self) -> None:
        self._client.close()

    def ping(self) -> tuple[bool, list[str]]:
        """Comprueba el servicio sin generar texto. Devuelve disponibilidad y nombres de modelos."""
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Ollama no respondió en %s: %s", self.base_url, exc)
            return False, []
        return True, _model_names(response.json())

    def list_models(self) -> list[str]:
        available, names = self.ping()
        if not available:
            raise OllamaUnavailable(
                f"No hay conexión con Ollama en {self.base_url}. "
                "Abre la aplicación Ollama y vuelve a intentar."
            )
        return names

    def ensure_model(self, model_name: str) -> None:
        names = self.list_models()
        if not model_installed(model_name, names):
            raise OllamaUnavailable(
                f"El modelo '{model_name}' no está en Ollama. "
                f"Modelos disponibles: {', '.join(names) or 'ninguno'}."
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Genera un vector por cada texto. Los textos ya deben traer el prefijo de nomic."""
        if not texts:
            return []
        self.ensure_model(self.embedding_model)
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start : start + EMBED_BATCH_SIZE]
            payload = self._post_json(
                "/api/embed",
                {"model": self.embedding_model, "input": batch, "keep_alive": "10m"},
            )
            vectors.extend(_read_embeddings(payload, expected=len(batch)))
        return vectors

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Pide una respuesta al modelo de lenguaje configurado."""
        self.ensure_model(self.llm_model)
        payload = self._post_json(
            "/api/chat",
            {
                "model": self.llm_model,
                "messages": messages,
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            },
        )
        message = payload.get("message") or {}
        content = str(message.get("content") or "").strip()
        if not content:
            raise OllamaUnavailable("Ollama respondió sin texto. Revisa el modelo configurado.")
        return content

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=body)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise OllamaUnavailable(
                f"No hay conexión con Ollama en {self.base_url}."
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaUnavailable(
                "Ollama no respondió a tiempo. En un equipo sin VRAM la generación tarda más."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:400]
            logger.error("Ollama devolvió %s en %s: %s", exc.response.status_code, path, detail)
            raise OllamaUnavailable(
                f"Ollama rechazó la solicitud ({exc.response.status_code})."
            ) from exc
        return response.json()


def model_installed(configured: str, installed: list[str]) -> bool:
    """Acepta el nombre corto. Ollama lista nomic-embed-text:latest si pediste nomic-embed-text."""
    wanted_name, _, wanted_tag = configured.partition(":")
    if not wanted_tag:
        wanted_tag = "latest"
    for item in installed:
        name, _, tag = item.partition(":")
        if not tag:
            tag = "latest"
        if name == wanted_name and tag == wanted_tag:
            return True
    return False


def _model_names(payload: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in payload.get("models") or []:
        name = item.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def _read_embeddings(payload: dict[str, Any], expected: int) -> list[list[float]]:
    raw = payload.get("embeddings")
    if raw is None and payload.get("embedding") is not None:
        raw = [payload["embedding"]]
    if not isinstance(raw, list) or len(raw) != expected:
        raise OllamaUnavailable("La respuesta de embeddings de Ollama no tiene la forma esperada.")
    vectors: list[list[float]] = []
    for item in raw:
        if not isinstance(item, list) or not item:
            raise OllamaUnavailable("Ollama devolvió un embedding vacío.")
        vectors.append([float(value) for value in item])
    return vectors
