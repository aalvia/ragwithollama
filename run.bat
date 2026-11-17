@echo off
cd /d "%~dp0"
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
if not exist ".venv\Scripts\python.exe" (
  echo No existe el entorno virtual. Ejecuta primero: python -m venv .venv
  exit /b 1
)
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8001
