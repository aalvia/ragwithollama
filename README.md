# AquaRAG

Asistente local de conocimiento para la industria camaronera. Responde en español usando los documentos de `data/documents/`, no la memoria general del modelo.

La página está en [http://127.0.0.1:8001](http://127.0.0.1:8001). En esta máquina el puerto 8000 ya lo ocupa otro programa local, por eso `run.bat` usa el 8001.

## Qué problema resuelve

Una finca acumula protocolos, costos y parámetros en archivos distintos. Preguntarle todo eso a un modelo pequeño, sin documentos, produce respuestas inventadas. AquaRAG hace otra cosa:

1. Parte los documentos en fragmentos.
2. `nomic-embed-text`, en Ollama, convierte cada fragmento en un vector.
3. ChromaDB guarda esos vectores en disco.
4. La pregunta se convierte en otro vector y se comparan.
5. Solo los fragmentos cercanos se le pasan a `qwen2.5:1.5b`.
6. La pantalla muestra la respuesta y el archivo de donde salió.

Si ningún fragmento es suficientemente cercano, la aplicación no llama al modelo. Responde que la base documental no alcanza.

## Arquitectura

```text
Navegador
    |
    |  HTTP, mismo proceso
    v
FastAPI  ----  servicios Python
                 |-- lectura de PDF, Word, Excel, Markdown
                 |-- embeddings, vía Ollama
                 |-- ChromaDB, en data/chroma_db
                 |-- respuesta, vía Ollama qwen2.5:1.5b
```

Los 20 Markdown iniciales los escribió el agente de desarrollo. La aplicación no genera documentos. Si agregas un archivo a `data/documents/`, el botón **Indexar documentos** lo incorpora.

## Tecnologías

| Pieza | Elección |
|---|---|
| Lenguaje | Python 3.12.10, el que ya estaba instalado |
| API | FastAPI, Uvicorn, Pydantic |
| Modelo de respuestas | `qwen2.5:1.5b` en el Ollama ya instalado |
| Embeddings | `nomic-embed-text` |
| Vectores | ChromaDB 1.5.9, carpeta local |
| Documentos | PyMuPDF, python-docx, openpyxl |
| Pantalla | HTML, CSS y JavaScript, servidos por FastAPI |

`qwen2.5:1.5b` está elegido porque el equipo de destino no tiene VRAM. `qwen2.5:7b` se puede usar después cambiando `OLLAMA_MODEL` y descargando ese modelo. No hace falta tocar el código.

## Requisitos

- Windows.
- Python 3.12.10 en `C:\Program Files\Python312\python.exe`. No hace falta actualizarlo.
- Ollama 0.40.16, el que ya está en `C:\Users\trabajo\AppData\Local\Programs\Ollama\`.
- Modelos locales: `qwen2.5:1.5b` y `nomic-embed-text`.
- Unos 400 MB libres para el entorno virtual. Los modelos viven en `C:\Users\trabajo\.ollama\models`.

## Instalación

En CMD, desde la carpeta del proyecto:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Ollama tiene que estar abierto. El modelo de embeddings, si falta:

```bat
ollama pull nomic-embed-text
```

`qwen2.5:1.5b` ya está en esta instalación. Compruébalo con `ollama list`.

## Configuración

El archivo `.env` controla la aplicación. Los valores que importan:

- `OLLAMA_MODEL=qwen2.5:1.5b`
- `OLLAMA_EMBEDDING_MODEL=nomic-embed-text`
- `CHUNK_SIZE=800` y `CHUNK_OVERLAP=150`
- `TOP_K=5`
- `MAX_DISTANCE=0.30`
- `CONVERSATION_CONTEXT=false`

`CONVERSATION_CONTEXT=false` hace que cada pregunta se responda sola. Si lo cambias a `true`, el servidor recuerda los últimos turnos de esa pestaña (`CONVERSATION_MAX_TURNS`, por defecto 4) y los usa para entender un seguimiento como «¿y en postlarvas?». Hay que reiniciar después de cambiar el `.env`. La memoria se borra al cerrar el servidor. No se guarda en disco.

`MAX_DISTANCE` se midió con este corpus. Las preguntas del tema quedaron entre 0,15 y 0,29. Las preguntas ajenas empezaron alrededor de 0,32. Un valor más alto deja pasar temas que no están en los documentos.

## Ejecución

```bat
run.bat
```

O, sin el archivo bat:

```bat
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Abre [http://127.0.0.1:8001](http://127.0.0.1:8001). La API también se puede ver en [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs).

La primera indexación de esta copia ya está hecha: 20 documentos y 213 fragmentos. Si borras `data/chroma_db`, vuelve a pulsar **Indexar documentos**.

Para indexar desde CMD:

```bat
.venv\Scripts\python.exe -m scripts.index_documents
.venv\Scripts\python.exe -m scripts.index_documents --full
```

`--full` recalcula todos los vectores. Sin esa opción, un archivo que no cambió no se vuelve a procesar.

## Cómo probarlo

Pruebas automáticas, sin Ollama:

```bat
.venv\Scripts\python.exe -m pytest -q
```

Pruebas que sí usan Ollama:

```bat
.venv\Scripts\python.exe -m pytest -q -m integration
```

En la página puedes preguntar:

- ¿Por qué el oxígeno disuelto baja antes del amanecer?
- ¿Cómo se calcula el factor de conversión alimenticia?
- ¿Cómo se calcula la densidad de siembra?
- ¿Qué es la mancha blanca y por qué una mancha no alcanza para diagnosticarla?
- ¿Qué prácticas de bioseguridad se aplican al entrar a una camaronera?
- ¿Qué cuidados siguen a la cosecha antes de llegar a la planta?
- ¿Cuál es la capital de Francia?

La última debe decir que la base documental no tiene información suficiente, y no debe mostrar fuentes.

## Lo que se comprobó en esta máquina

- 24 pruebas unitarias en verde.
- 3 pruebas de integración con Ollama en verde.
- Indexación real: 20 archivos, 213 fragmentos, en unos 7 segundos con los modelos ya cargados.
- Segunda indexación: 20 archivos sin cambios y 0 fragmentos reescritos.
- Preguntas reales sobre oxígeno, FCR y densidad de siembra, con el documento correcto como fuente.
- Pregunta sobre la capital de Francia rechazada sin llamar al modelo.
- `GET /api/health` en estado `ok`, con Ollama, los dos modelos y ChromaDB disponibles.
- La página, el CSS, el JavaScript, el listado y el estado respondieron 200 al abrir `http://127.0.0.1:8001`.

No se pudo hacer clic dentro del navegador automatizado: la herramienta del navegador no se conectó en esta sesión. El contrato que usa `app.js` sí se ejerció contra el servidor en marcha.

## Problemas comunes

**`ollama` no se reconoce.** Esta ventana de CMD se abrió antes de instalar Ollama. Cierra y abre CMD, o usa la ruta `C:\Users\trabajo\AppData\Local\Programs\Ollama\ollama.exe`. `run.bat` agrega esa carpeta al PATH de esa ejecución.

**El puerto 8001 no abre.** Mira la consola de Uvicorn. Si dice que la dirección ya está en uso, cambia el puerto al final de `run.bat`.

**ChromaDB no instala.** La versión 0.6.3 intentó compilar `chroma-hnswlib` y esta máquina no tiene el compilador de C++. `requirements.txt` fija ChromaDB 1.5.9, que trae rueda para Windows y Python 3.12. Instala con:

```bat
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
```

**El modelo de embeddings no aparece.** `ollama list` debe mostrar `nomic-embed-text`. El programa acepta tanto `nomic-embed-text` como `nomic-embed-text:latest`.

**Cambié de modelo de embeddings y ChromaDB falla.** La carpeta fue creada con otro modelo. Borra `data/chroma_db` y `data/index_state.json`, y vuelve a indexar.

**Una pregunta del tema dice que no hay información.** La distancia superó `MAX_DISTANCE`. Sube un poco ese valor en `.env`, reinicia y pregunta otra vez. No lo subas hasta 0,55: en esta base las preguntas ajenas empiezan cerca de 0,32.

**La respuesta es pobre.** El modelo es de 1,5B y solo puede usar los fragmentos recuperados. Revisa las fuentes que muestra la pantalla. Si la fuente es la correcta y el texto es flojo, el límite es el modelo, no la búsqueda.
