"""Indexa la carpeta data/documents desde la consola.

Uso, desde la raíz del proyecto:
    .venv\\Scripts\\python.exe -m scripts.index_documents
    .venv\\Scripts\\python.exe -m scripts.index_documents --full
"""

from __future__ import annotations

import argparse

from app.config import get_settings
from app.main import build_services


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa los documentos de AquaRAG en ChromaDB.")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Vuelve a calcular los vectores de todos los archivos.",
    )
    args = parser.parse_args()
    services = build_services(get_settings())
    try:
        report = services["indexer"].index(full=args.full)
    finally:
        services["ollama"].close()
    print(f"Nuevos: {len(report.added)}")
    print(f"Modificados: {len(report.updated)}")
    print(f"Eliminados: {len(report.removed)}")
    print(f"Sin cambios: {len(report.unchanged)}")
    print(f"Fragmentos escritos: {report.chunks_written}")
    print(f"Errores: {len(report.errors)}")
    for error in report.errors:
        print(f"  - {error}")
    print(f"Segundos: {report.duration_seconds}")


if __name__ == "__main__":
    main()
