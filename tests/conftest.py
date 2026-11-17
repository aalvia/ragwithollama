"""Aísla las pruebas de la carpeta real de documentos y de ChromaDB."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "tests" / "_tmp"
(TMP / "documents").mkdir(parents=True, exist_ok=True)
(TMP / "chroma").mkdir(parents=True, exist_ok=True)

os.environ["CHROMA_DB_PATH"] = str(TMP / "chroma")
os.environ["DOCUMENTS_PATH"] = str(TMP / "documents")
os.environ["INDEX_STATE_PATH"] = str(TMP / "index_state.json")
os.environ["CONVERSATION_CONTEXT"] = "false"
