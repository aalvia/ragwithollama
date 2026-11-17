"""Errores de aplicación con un mensaje claro para la API."""


class AquaRAGError(Exception):
    """Error controlado que la API puede mostrar al usuario."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class OllamaUnavailable(AquaRAGError):
    """Ollama no acepta conexiones o no tiene el modelo pedido."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=503)
