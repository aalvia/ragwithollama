# Manual de implementación

Este manual explica cómo volver a construir AquaRAG desde cero en Windows, con el Python y el Ollama que ya están instalados. Cada etapa dice para qué existe, qué código la sostiene y qué fallo apareció en esta máquina.

Python usado: 3.12.10, `C:\Program Files\Python312\python.exe`.
Ollama usado: 0.40.16, `C:\Users\trabajo\AppData\Local\Programs\Ollama\ollama.exe`.
Modelo de respuestas: `qwen2.5:1.5b`, ya descargado.
Modelo de embeddings: `nomic-embed-text`.

No se actualizó Python. No se instaló otro Ollama.

## 1. Verificar Python

**Objetivo.** Saber qué intérprete va a crear el entorno virtual.

```bat
python --version
py --list
where python
```

En esta máquina la salida fue Python 3.12.10, una sola instalación de 64 bits, en `C:\Program Files\Python312\python.exe`.

**Por qué.** Una librería puede fallar en 3.11 y funcionar en 3.12, o al revés. El entorno virtual copia este intérprete. No lo reemplaza.

**Resultado esperado.** Una sola versión, la 3.12.

**Error habitual.** `python` apunta a otra instalación por el orden del PATH. `where python` muestra la ruta real. Si aparecen dos, el `python` de la primera línea es el que usará `venv`.

## 2. Crear el entorno virtual

**Objetivo.** Instalar FastAPI y ChromaDB sin tocar el Python del sistema ni el proyecto de `G:\mar`.

```bat
cd /d "G:\erp rag"
python -m venv .venv
```

**Por qué.** `venv` crea una carpeta `.venv` con su propio `python.exe` y su propio `site-packages`. El intérprete base sigue siendo 3.12.10.

**Resultado esperado.** Existe `.venv\Scripts\python.exe`.

**Error habitual.** Crear el entorno con `py -3.11` u otro lanzador. Aquí solo está 3.12, así que `python -m venv .venv` basta.

## 3. Instalar dependencias

**Objetivo.** Tener FastAPI, ChromaDB y los lectores de documentos en el entorno.

El archivo `requirements.txt` fija versiones. ChromaDB va en 1.5.9, no en 0.6.3.

```bat
.venv\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
```

**Por qué cada pieza.**

- FastAPI recibe la pregunta y devuelve JSON.
- Uvicorn es el proceso que escucha el puerto.
- Pydantic valida el cuerpo de `/api/chat` y la forma de la respuesta.
- httpx llama al Ollama local.
- ChromaDB guarda vectores.
- PyMuPDF lee PDF. python-docx lee Word. openpyxl lee Excel.
- pytest ejecuta las pruebas.

**Resultado esperado.** `pip` termina sin pedir Visual C++.

**Error habitual.** Con `chromadb==0.6.3`, pip intentó compilar `chroma-hnswlib` y falló: no hay Microsoft Visual C++ en esta máquina. ChromaDB 1.5.9 publica una rueda `win_amd64` usable en Python 3.12. `--only-binary=:all:` impide que pip vuelva a intentar una compilación.

## 4. Usar el Ollama que ya está

**Objetivo.** Confirmar el servidor local, sin instalar otro.

Ollama 0.40.16 ya corría por el proyecto de `G:\mar`. La API es `http://127.0.0.1:11434`. En una CMD nueva, `ollama` a veces no está en el PATH hasta que se refresca. La ruta directa funciona:

```bat
"%LOCALAPPDATA%\Programs\Ollama\ollama.exe" --version
"%LOCALAPPDATA%\Programs\Ollama\ollama.exe" list
```

**Por qué Ollama.** Expone un modelo en la propia máquina. No hay clave de API ni cobro por token.

**Resultado esperado.** La versión 0.40.16 y, en la lista, `qwen2.5:1.5b`.

**Error habitual.** `ollama` no se reconoce. No es que falte el programa. Falta el PATH de esa ventana. `run.bat` lo agrega solo para esa ejecución.

## 5. Dejar listo el modelo de respuestas

**Objetivo.** Usar `qwen2.5:1.5b`, que ya está descargado.

No se descarga `qwen2.5:7b`. El equipo de destino no tiene VRAM, y 7B en CPU hace lenta la demo. El nombre queda en `.env`:

```text
OLLAMA_MODEL=qwen2.5:1.5b
```

**Por qué un modelo chico.** La búsqueda la hace el embedding. El modelo solo redacta con los fragmentos que ChromaDB devolvió. Si más adelante hay memoria y GPU, se cambia la variable y se descarga el modelo mayor.

**Resultado esperado.** `ollama list` muestra `qwen2.5:1.5b`.

**Error habitual.** Escribir `qwen2.5:7b` en `.env` sin haberlo descargado. `/api/health` queda `degraded` y el chat responde 503 con el nombre del modelo que falta.

## 6. Descargar nomic-embed-text

**Objetivo.** Tener un modelo que convierta texto en vectores. `qwen2.5:1.5b` no sirve para eso: Ollama lo anuncia solo con capacidad de completar texto.

```bat
ollama pull nomic-embed-text
```

En esta máquina la descarga fue de 274 MB. `ollama list` lo muestra como `nomic-embed-text:latest`. El programa acepta el nombre corto `nomic-embed-text` porque `model_installed` en `app/services/ollama_service.py` trata la etiqueta vacía como `latest`.

**Por qué este modelo.** Es pequeño, corre en CPU y la búsqueda de este proyecto es de español a español. Además exige un prefijo, aplicado en `embedding_service.py`:

```python
DOCUMENT_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
```

El texto guardado en ChromaDB no lleva el prefijo. El prefijo solo entra al vector. Así la pantalla muestra el fragmento limpio y la búsqueda usa el formato que el modelo espera.

**Resultado esperado.** Un embedding de prueba tiene cientos de números. En la prueba de integración se exige `len(vector) > 100`.

**Error habitual.** Indexar antes de terminar el `pull`. El servicio lanza `OllamaUnavailable` y la API responde 503.

## 7. Crear la estructura

**Objetivo.** Separar la API, el cálculo y el almacén, sin capas de más.

```text
app/main.py                 arranca FastAPI y arma los objetos
app/config.py               lee .env
app/api/routes/             chat, documents, health
app/services/               Ollama, embeddings, documentos, índice, RAG, memoria
app/repositories/           ChromaDB
app/schemas/                formas de entrada y salida
app/frontend/               HTML, CSS, JavaScript
data/documents/             los 20 Markdown
data/chroma_db/             vectores
scripts/index_documents.py  indexar desde CMD
```

La memoria de conversación está en `conversation_service.py` porque el `.env` la enciende o la apaga, y no es responsabilidad de ChromaDB.

**Resultado esperado.** `uvicorn app.main:app` importa el paquete `app` desde la raíz del proyecto.

**Error habitual.** Ejecutar Uvicorn desde otra carpeta. Las rutas de `.env` se resuelven contra la raíz del proyecto (`ROOT_DIR` en `config.py`), no contra el directorio actual. Aun así, el comando se lanza desde la raíz para que `app` sea importable.

## 8. Crear el procesador documental

**Objetivo.** Leer PDF, Word, Excel, TXT y Markdown sin copiar la lógica dentro de la ruta HTTP.

La clase `DocumentService` vive en `app/services/document_service.py`. Recorre `data/documents/` con `rglob`, ignora temporales (`~$`, archivos ocultos) y acepta `.md`, `.txt`, `.pdf`, `.docx` y `.xlsx`.

`extract_blocks` devuelve tuplas `(sección, página, texto)`. La página solo existe en PDF, porque PyMuPDF lee hoja por hoja. El Markdown se parte por líneas que empiezan con `#`, para que un fragmento de «Mancha blanca» no se mezcle con el glosario.

`file_hash` calcula SHA-256 de los bytes del archivo. Ese hash decide si el archivo cambió.

**Por qué pathlib.** Recorre carpetas anidadas sin armar rutas a mano. En Windows devuelve la ruta relativa con barras `/` (`as_posix`), y esa cadena es la que se guarda en ChromaDB.

**Resultado esperado.** Una prueba crea un PDF, un DOCX y un XLSX temporales y encuentra una frase conocida en cada uno. Está en `tests/test_document_processing.py`.

**Error habitual.** Un Word antiguo `.doc` no entra. Hace falta guardarlo como `.docx`. Un PDF escaneado, de solo imagen, sale vacío: PyMuPDF no hace OCR en este proyecto.

## 9. Implementar el chunking

**Objetivo.** Que cada fragmento quepa en el embedding y, a la vez, conserve el tema.

`split_text` corta cerca de 800 caracteres, con 150 de solape. Prefiere cortar en un párrafo, un salto de línea o un punto, si el corte cae en la segunda mitad de la ventana. El solape existe para que una frase partida en el borde aparezca en los dos fragmentos.

`compose_chunk_text` antepone el nombre del archivo y la sección:

```text
Documento: oxigeno_disuelto_temperatura.md
Sección: Qué hace bajar el oxígeno

La respiración nocturna de una floración densa.
```

Ese texto es el que se vectoriza y el que ve el modelo. La sección mejora la búsqueda: la pregunta y el fragmento comparten las mismas palabras de título.

**Por qué 800 y 150.** Son los valores pedidos, y caben de sobra en el contexto de `nomic-embed-text`. Están en `.env` para poder moverlos sin editar el código. Si se cambian, hay que reindexar con `--full`, porque los fragmentos viejos fueron cortados con el tamaño anterior.

**Resultado esperado.** Un texto largo produce más de un fragmento, y ninguno supera el tamaño. Un texto en blanco, después de `strip`, produce una lista vacía.

**Error habitual.** Un solape igual o mayor que el tamaño. `Settings` lo rechaza al arrancar. Sin ese control, el bucle de corte no avanza.

## 10. Implementar los embeddings

**Objetivo.** Convertir fragmentos y preguntas en vectores comparables, usando solo Ollama.

`EmbeddingService.embed_documents` pone el prefijo `search_document: `. `embed_query` pone `search_query: `. `OllamaService.embed` envía lotes de 16 textos a `POST /api/embed` y lee la lista `embeddings`.

```python
payload = self._post_json(
    "/api/embed",
    {"model": self.embedding_model, "input": batch, "keep_alive": "10m"},
)
```

`keep_alive` deja el modelo cargado durante la indexación, para no pagarlo en cada lote.

**Por qué no deja que ChromaDB embeba solo.** La instalación por defecto de ChromaDB descarga otro modelo. Aquí el único modelo de vectores es el de Ollama. ChromaDB recibe el vector ya calculado.

**Resultado esperado.** La prueba de integración obtiene un vector numérico y, después, una búsqueda que acierta el archivo.

**Error habitual.** La respuesta trae la clave `embedding` en singular. `_read_embeddings` acepta las dos formas. Si el lote no trae tantos vectores como textos, se lanza un error en lugar de guardar un índice a medias.

## 11. Implementar ChromaDB

**Objetivo.** Guardar el vector, el texto y el origen, y sobrevivir a un reinicio.

`VectorRepository` abre `chromadb.PersistentClient` sobre `data/chroma_db`. La colección se llama `aquarag`. El espacio es coseno:

```python
metadata={"hnsw:space": "cosine", "embedding_model": self.embedding_model}
```

En coseno, distancia 0 es el mismo significado. Una distancia menor es un fragmento más cercano. Antes de crear la colección se desactiva la telemetría anónima de ChromaDB con la variable `ANONYMIZED_TELEMETRY`.

Cada fragmento guarda metadatos de tipos simples, porque ChromaDB no acepta listas ni `None`:

- `source_name`, `source_path`, `heading`, `indexed_at`, `content_hash`
- `page`: número de página, o `-1` si el archivo no tiene páginas
- `chunk_index`

`replace_document` borra los fragmentos de ese archivo y escribe los nuevos. `query` pide como máximo `top_k` resultados, y nunca más de los que hay en la colección. Pedir 5 cuando hay 2 hace fallar a ChromaDB.

**Por qué ChromaDB.** Hay que guardar los vectores entre una pregunta y la siguiente, buscar los vecinos y devolver el nombre del archivo. Con 213 fragmentos la cuenta es pequeña. La librería evita escribir a mano el índice, el borrado por archivo y la persistencia.

**Resultado esperado.** Después de indexar, `vectors.count()` devuelve 213. Al reiniciar la aplicación, el conteo sigue ahí.

**Error habitual.** Cambiar `OLLAMA_EMBEDDING_MODEL` y reutilizar la carpeta. El repositorio compara `embedding_model` y pide borrar `data/chroma_db`. Mezclar vectores de dos modelos no tiene sentido: no viven en el mismo espacio.

## 12. Implementar la recuperación

**Objetivo.** Quedarse solo con fragmentos que de verdad hablen del tema.

`RagService.answer` embebe la pregunta, consulta ChromaDB con `TOP_K=5` y descarta lo que supere `MAX_DISTANCE`. El valor 0,30 salió de medir este corpus:

| Pregunta | Mejor distancia | Archivo |
|---|---|---|
| Oxígeno antes del amanecer | 0,228 | `oxigeno_disuelto_temperatura.md` |
| Cómo se calcula el FCR | 0,202 | `conversion_alimenticia_fcr.md` |
| Densidad de siembra | 0,181 | `densidad_de_siembra.md` |
| Capital de Francia | 0,365 | un archivo de cosecha, descartado |

`plan_index_actions` decide qué archivos tocan el índice. Compara el hash del disco con el hash guardado en `data/index_state.json`.

- Hash nuevo: se indexa.
- Hash distinto: se reemplaza.
- Hash igual: no se llama a Ollama.
- El archivo ya no está: se borran sus vectores.

Si la colección está vacía, se reconstruye aunque el JSON diga que ya estaba indexado. `--full` hace lo mismo a propósito.

**Resultado esperado.** La segunda indexación de los 20 archivos reporta 20 sin cambios y 0 fragmentos escritos. Así ocurrió en esta máquina.

**Error habitual.** Borrar `data/chroma_db` y dejar `index_state.json`. El código lo contempla: si el conteo de vectores es 0, trata los archivos como pendientes y los vuelve a embeber.

## 13. Implementar la generación de respuestas

**Objetivo.** Redactar solo con los fragmentos aceptados.

Si la lista filtrada queda vacía, `RagService` devuelve un texto fijo y no llama a Ollama. Eso es deliberado. Un modelo de 1,5B, sin fragmentos, responde con lo que trae de fábrica. La prueba de «capital de Francia» tardó 0,18 segundos y no mostró fuentes.

Si hay fragmentos, `build_messages` arma:

1. El prompt de sistema, en `SYSTEM_PROMPT`. Pide español, cifras solo del contexto, y prohíbe diagnóstico y dosis.
2. Los turnos previos, únicamente si `CONVERSATION_CONTEXT=true`.
3. Un mensaje de usuario con los fragmentos numerados y la pregunta.

Ollama recibe eso en `POST /api/chat`, con temperatura 0,1 y un tope de 700 tokens. La temperatura baja reduce invenciones. El tope evita una respuesta eterna en CPU.

Las fuentes que ve la pantalla no salen del texto libre del modelo. Salen de `to_source`, es decir, de los metadatos de ChromaDB.

Cuando el contexto está apagado, `build_search_text` busca solo con la pregunta actual. Cuando está encendido, la búsqueda concatena la pregunta anterior, para que «¿y en postlarvas?» siga el tema.

**Resultado esperado.** Una pregunta de densidad cita `densidad_de_siembra.md` y escribe la fórmula animales / área. Así respondió el servidor en `http://127.0.0.1:8001/api/chat`.

**Error habitual.** Confiar en que el modelo «se va a contener» sin el corte de distancia. Con el umbral en 0,55, la pregunta de la capital de Francia igual recuperaba fragmentos de cosecha y el modelo contestaba.

## 14. Crear la API

**Objetivo.** Exponer el flujo por HTTP, con validación y errores claros.

| Método y ruta | Función |
|---|---|
| `POST /api/chat` | Pregunta, respuesta, fuentes, documentos y segundos |
| `POST /api/documents/index` | Indexa lo nuevo o lo modificado. `?full=true` rehace todo |
| `GET /api/documents` | Lista archivos y si están indexados, modificados o pendientes |
| `GET /api/documents/stats` | Conteos, última indexación, modelos y estado de Ollama |
| `GET /api/health` | FastAPI, Ollama, los dos modelos y ChromaDB |

`ChatRequest` exige una pregunta de 2 a 2000 caracteres. Una pregunta vacía responde 422, no llega a Ollama.

`OllamaUnavailable` se traduce a HTTP 503 con un mensaje en español. Cualquier otra excepción no prevista responde 500 y deja el detalle en el log, no en el navegador.

`build_services` en `main.py` es el único lugar que une configuración, Ollama, documentos, ChromaDB, índice, memoria y RAG. Las rutas leen `request.app.state`. No crean conexiones por su cuenta.

**Resultado esperado.** `GET /api/health` devuelve `"status": "ok"` cuando Ollama tiene los dos modelos y ChromaDB abre.

**Error habitual.** Un `POST /api/documents/index` largo en una laptop sin GPU. El navegador debe esperar. El botón se desactiva mientras dura. No hay generación de documentos en esta API: los Markdown ya están en la carpeta.

## 15. Crear el frontend

**Objetivo.** Preguntar sin Postman.

`app/frontend/index.html`, `styles.css` y `app.js` los sirve el mismo FastAPI. `/` entrega el HTML. `/static` entrega CSS y JavaScript. No hay React ni una herramienta de Node.

`app.js` hace cuatro cosas:

- Al cargar, pide `/api/documents/stats`, `/api/documents` y `/api/health`.
- Al enviar, hace `POST /api/chat` con la pregunta y un `session_id` guardado en `sessionStorage`.
- Enter envía. Shift+Enter deja un salto de línea.
- Debajo de la respuesta crea un bloque por fuente: archivo, página si existe, identificador del fragmento, distancia y extracto.

El texto se inserta con `textContent`, no con HTML del modelo. Así una respuesta no puede inyectar una etiqueta.

El aviso «Contexto de conversación: apagado» sale del campo `conversation_context` de la API. Cambiar el `.env` y reiniciar cambia el aviso.

**Resultado esperado.** Al abrir la página, el panel muestra 20 documentos, 213 fragmentos, Ollama disponible y `qwen2.5:1.5b`.

**Error habitual.** Abrir el HTML con doble clic, como archivo. El navegador no puede llamar a `/api`. Hay que entrar por `http://127.0.0.1:8001`.

## 16. Ejecutar y probar

**Objetivo.** Ver el sistema completo, no solo los módulos sueltos.

```bat
run.bat
```

Luego:

```bat
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q -m integration
```

La suite normal no llama a Ollama. La marcada `integration` sí, y por eso `pytest.ini` la excluye del comando corto.

Comprobaciones hechas aquí:

1. Ollama responde y lista los dos modelos.
2. Un embedding devuelve un vector.
3. PDF, DOCX, XLSX y Markdown se leen en pruebas que crean el archivo en un temporal.
4. El corte de fragmentos respeta el tamaño.
5. ChromaDB guarda y una pregunta recupera `oxigeno.md` o `fcr.md` en la prueba de integración.
6. La capital de Francia no produce fuentes.
7. La API rechaza la pregunta vacía, devuelve 503 si Ollama falla y lista documentos.
8. El JavaScript contiene las rutas `/api/chat` y `/api/documents/index`.
9. Contra el servidor real, la densidad de siembra citó solo `densidad_de_siembra.md`.

**Error habitual.** Correr las pruebas de integración con Ollama cerrado. Fallan en `ping`, no en la lógica de fragmentos. Abre Ollama y repite solo `-m integration`.
