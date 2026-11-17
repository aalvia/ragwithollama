# Guía del código

Cada archivo de abajo es el que está en el repositorio. Las funciones se describen con los parámetros y el retorno reales.

## app/config.py

**Responsabilidad.** Leer `.env` y resolver las rutas contra la carpeta del proyecto, no contra el directorio desde el que se lanzó el comando.

**Clase `Settings`.** Campos principales: `ollama_base_url`, `ollama_model`, `ollama_embedding_model`, `ollama_timeout_seconds`, `ollama_temperature`, `ollama_max_tokens`, `chroma_db_path`, `documents_path`, `index_state_path`, `chunk_size`, `chunk_overlap`, `top_k`, `max_distance`, `conversation_context`, `conversation_max_turns`.

`chunk_overlap` tiene que ser menor que `chunk_size`. `top_k` va de 1 a 20. `conversation_context` acepta `true` o `false`.

**`path(value)`** devuelve un `Path` absoluto. Si `value` es relativo, lo une a `ROOT_DIR`.

**`chroma_path`, `documents_dir`, `index_state_file`.** Atajos de esas tres rutas.

**`get_settings()`** devuelve una sola instancia, con caché. Un cambio en `.env` se ve al reiniciar el proceso.

**Dependencias.** `pydantic_settings`.

## app/errors.py

**`AquaRAGError(message, status_code=500)`.** Error que la API puede mostrar.

**`OllamaUnavailable(message)`.** Subclase con código 503. La lanzan las llamadas a Ollama cuando no hay conexión, falta el modelo o la respuesta viene vacía.

## app/main.py

**Responsabilidad.** Construir los objetos una vez y servir HTTP más la página.

**`configure_logging()`** deja el log en INFO y calla el ruido de `httpx` y `chromadb`.

**`build_services(settings)`** crea, en orden, `OllamaService`, `EmbeddingService`, `DocumentService`, `VectorRepository`, `IndexingService`, `ConversationMemory` y `RagService`. Devuelve un diccionario. Las pruebas de integración llaman a esta función con rutas temporales. Crea las carpetas de documentos y de ChromaDB si no existen.

**`create_app()`** registra las rutas, el manejador de `AquaRAGError`, el manejador de excepciones imprevistas, `GET /` y `/static`. En el arranque llama a `build_services`. Al cerrar, cierra el cliente HTTP de Ollama.

**Dependencias.** FastAPI, las rutas y los servicios.

**Flujo.** Uvicorn importa `app`. El primer request espera a que el lifespan haya colgado los servicios en `app.state`.

## app/services/ollama_service.py

**Responsabilidad.** Hablar con el Ollama local.

**`OllamaService.__init__(...)`** guarda la URL, los dos nombres de modelo, la temperatura y el tope de tokens. Abre un `httpx.Client` con tiempo de conexión corto y tiempo de lectura igual a `OLLAMA_TIMEOUT_SECONDS`.

**`ping()`** devuelve `(True, nombres)` o `(False, [])`. Usa un timeout de 5 segundos. No lanza excepción. Lo usa `/api/health`.

**`list_models()`** llama a `ping` y, si no hay servicio, lanza `OllamaUnavailable`.

**`ensure_model(model_name)`** exige que el modelo esté instalado.

**`embed(texts)`** devuelve una lista de vectores. Parte la entrada en lotes de 16. El texto ya debe traer el prefijo de nomic.

**`chat(messages)`** devuelve el texto de la respuesta. Envía `temperature` y `num_predict`.

**`model_installed(configured, installed)`** compara nombre y etiqueta. Si el configurado no trae etiqueta, usa `latest`. Así `nomic-embed-text` coincide con `nomic-embed-text:latest`, y `qwen2.5:1.5b` no coincide con un hipotético `qwen2.5:7b`.

## app/services/embedding_service.py

**`with_prefix(text, purpose)`** devuelve el texto con `search_document: ` o `search_query: `. Si el prefijo ya está, no lo duplica.

**`EmbeddingService.embed_documents(texts)`** devuelve un vector por fragmento.

**`embed_query(text)`** devuelve un solo vector.

**Dependencia.** `OllamaService`. No conoce ChromaDB.

## app/services/document_service.py

**Responsabilidad.** Encontrar archivos y convertirlos en fragmentos.

**`DocumentService.list_files()`** devuelve `FoundFile`: ruta, ruta relativa, nombre, extensión, tamaño y hash.

**`build_chunks(document)`** devuelve `Chunk`. El `chunk_id` tiene la forma `ruta::c0000`. El texto incluye documento y sección.

**`file_hash(path)`** devuelve el SHA-256 hexadecimal de los bytes.

**`clean_text(text)`** devuelve el texto sin caracteres de control y sin bloques enormes de líneas vacías.

**`split_text(text, size, overlap)`** devuelve la lista de fragmentos. Recorta espacios. Corta en párrafo, línea o punto cuando puede.

**`split_markdown_sections(text)`** devuelve pares `(título, cuerpo)`.

**`extract_blocks(path, extension)`** devuelve `(sección, página, texto)`. Página `None` fuera de los PDF.

**Dependencias.** PyMuPDF (`fitz`), python-docx, openpyxl.

**Ejemplo.** Un Markdown con dos títulos produce al menos dos bloques, y cada chunk resultante empieza por `Documento:`.

## app/services/indexing_service.py

**`plan_index_actions(found_hashes, indexed_hashes)`** es pura. Recibe dos diccionarios ruta → hash y devuelve listas `added`, `updated`, `removed`, `unchanged`. No toca disco ni Ollama. La prueba unitaria cubre los cuatro casos.

**`IndexingService.index(full=False)`** devuelve `IndexReport`. Si `full` es verdadero o la colección está vacía, reconstruye. Por cada archivo nuevo o modificado embebe, reemplaza vectores y actualiza `data/index_state.json`. Si Ollama no está, la excepción sale hacia la API. Otro error de un archivo se anota en `report.errors` y el resto sigue. El JSON se guarda también si la corrida se interrumpe, para no perder lo ya escrito.

**`list_documents()`** devuelve cada archivo con estado `indexed`, `modified` o `pending`.

**`stats()`** devuelve conteos, la última fecha, los nombres de modelo y si Ollama responde. El flag de conversación lo completa la ruta, porque el índice no posee la memoria.

**Dependencias.** `DocumentService`, `EmbeddingService`, `VectorRepository`, `OllamaService`.

## app/repositories/vector_repository.py

**`VectorRepository(persist_path, embedding_model)`** abre la colección `aquarag`. Si la colección existe con otro modelo de embeddings, lanza `RuntimeError` con la instrucción de borrar la carpeta.

**`count()`** devuelve el número de fragmentos.

**`replace_document(source_path, ids, embeddings, documents, metadatas)`** borra los ids de ese archivo y hace `upsert`. Si la lista viene vacía, solo borra.

**`delete_document(source_path)`** borra por el metadato `source_path`.

**`query(embedding, top_k)`** devuelve `StoredChunk`, con `page` en `None` cuando el metadato vale `-1`. Pide `min(top_k, count)` resultados.

**Dependencia.** ChromaDB 1.5.9. `list_collections` puede devolver nombres o objetos. `_collection_names` acepta los dos.

## app/services/conversation_service.py

**`ConversationMemory(enabled, max_turns)`.**

**`history(session_id)`** devuelve una copia de los turnos. Si `enabled` es falso o no hay sesión, devuelve lista vacía.

**`remember(session_id, question, answer)`** agrega el par y recorta a `max_turns * 2` mensajes. Con el contexto apagado no guarda nada.

**Ejemplo.** Con `enabled=False`, dos preguntas seguidas buscan solo el texto de cada una. Con `enabled=True` y `max_turns=2`, la segunda búsqueda incluye la primera pregunta, y una tercera recorta la historia a cuatro mensajes. Las pruebas están en `tests/test_rag.py`.

## app/services/rag_service.py

**Constante `SYSTEM_PROMPT`.** Instrucciones en español: solo fragmentos, sin cifras inventadas, sin diagnóstico, citar el archivo.

**Constante `INSUFFICIENT_ANSWER`.** Texto fijo cuando no hay fragmentos bajo el umbral.

**`RagService.answer(question, session_id=None)`** devuelve `ChatResponse`. Mide el tiempo. Filtra por `max_distance`. Llama a `chat` solo si quedó algún fragmento. Después, si corresponde, recuerda el turno.

**`build_search_text(question, history)`** devuelve la pregunta, o la pregunta anterior más la actual.

**`build_messages(question, chunks, history)`** devuelve la lista de mensajes para Ollama. Recorta cada turno previo a 700 caracteres.

**`build_user_prompt(question, chunks)`** numera los fragmentos con archivo y página.

**`to_source(hit)`** convierte un `StoredChunk` en `SourceItem`. El extracto se compacta a 500 caracteres. La distancia se redondea a 4 decimales.

**Dependencias.** Ollama, embeddings, vectores y memoria.

## app/schemas/chat.py y app/schemas/documents.py

**`ChatRequest`.** `question` de 2 a 2000 caracteres. `session_id` opcional, hasta 80.

**`ChatResponse`.** `question`, `answer`, `sources`, `related_documents`, `processing_seconds`, `conversation_context`, `used_retrieval`.

**`SourceItem`.** `document`, `path`, `page`, `chunk_id`, `heading`, `excerpt`, `distance`.

**`DocumentItem`.** Incluye `status`: `indexed`, `modified` o `pending`.

**`IndexReport`.** Listas de agregados, actualizados, eliminados, sin cambios y errores, más fragmentos escritos y segundos.

**`StatsResponse` y `HealthResponse`.** Los campos que muestra el panel y el botón de estado.

No hay lógica aquí. Si el JSON no cumple, FastAPI responde 422 antes de entrar a la ruta.

## app/api/routes/chat.py

**`POST /api/chat`.** Recibe `ChatRequest`, llama a `request.app.state.rag.answer` y devuelve `ChatResponse`.

## app/api/routes/documents.py

**`GET /api/documents`.** Lista archivos.

**`GET /api/documents/stats`.** Estadísticas. Copia `conversation_context` desde la memoria.

**`POST /api/documents/index`.** Query `full`, por defecto falso. No exige cuerpo. El botón de la página hace `POST` sin JSON.

## app/api/routes/health.py

**`GET /api/health`.** No genera texto. Usa `ping`, `model_installed` y `vectors.count()`. Si ChromaDB lanza, `chromadb` queda en `error` y el estado general en `degraded`. Si Ollama está cerrado, la ruta sigue respondiendo 200 con `status: degraded`. El chat, en cambio, responde 503, porque ahí sí hace falta el modelo.

## app/frontend/index.html, styles.css, app.js

**Responsabilidad.** Una pantalla con la conversación y un panel de documentos.

**`sessionId()`** crea un UUID en `sessionStorage` la primera vez.

**`sendQuestion(question)`** hace `POST /api/chat`. Mientras espera, muestra un mensaje de proceso. Al volver, pinta la respuesta y un bloque por fuente.

**`refreshInfo()`** lee estadísticas y la lista.

**`refreshHealth()`** escribe el estado en el panel.

Enter envía el formulario. Shift+Enter no. Los botones llaman a indexar, refrescar y consultar estado. El botón de indexar se desactiva hasta que el servidor responde.

**Dependencias.** Ninguna librería de JavaScript. Solo `fetch`.

## scripts/index_documents.py

Se ejecuta con `python -m scripts.index_documents` desde la raíz. Acepta `--full`. Usa `build_services` y cierra el cliente de Ollama al terminar. Imprime conteos en la consola.

## tests/conftest.py

Antes de importar la aplicación, apunta `CHROMA_DB_PATH`, `DOCUMENTS_PATH` e `INDEX_STATE_PATH` a `tests/_tmp`. Las pruebas de API no escriben en el índice real de los 20 documentos.

## tests/test_document_processing.py

Cubre limpieza, corte, títulos de Markdown, extracción de PDF, DOCX y XLSX, el prefijo de documento dentro del chunk, y `plan_index_actions`. Los binarios se crean en un directorio temporal. No usa Ollama.

## tests/test_rag.py

Usa dobles en lugar de Ollama y de ChromaDB. Comprueba el prefijo de nomic, el nombre `latest`, la búsqueda con y sin memoria, que una distancia de 0,92 no llama al modelo, que una distancia de 0,21 devuelve la fuente, y que la memoria apagada no reutiliza la pregunta anterior.

## tests/test_api.py

Levanta `TestClient`. Sustituye `app.state` para no depender de Ollama. Comprueba la página, el chat, el 422, el 503, el listado, el estado degradado y que `app.js` contiene las rutas que el cliente llama.

## tests/test_integration_ollama.py

Marcadas con `integration`. Escriben dos Markdown en un temporal, indexan contra el Ollama real y comprueban el archivo recuperado, el rechazo de una pregunta ajena y que la segunda indexación no reescribe fragmentos. `pytest.ini` las deja fuera del `pytest` normal.

## Flujo de ejecución completo

`run.bat` entra a la carpeta del proyecto, agrega Ollama al PATH y lanza Uvicorn en `127.0.0.1:8001`.

Uvicorn importa `app`. El lifespan lee `.env`, abre ChromaDB y deja los servicios en memoria. No indexa solo. El índice ya existe o lo dispara la persona.

El navegador carga `/`. `app.js` pide estadísticas, lista y salud. Al enviar una pregunta, `chat.py` llama a `RagService.answer`. Ese servicio pide un vector, consulta `VectorRepository`, y solo entonces `OllamaService.chat`. La respuesta vuelve como JSON y la página pinta texto y fuentes.

Indexar recorre el mismo camino hasta los embeddings, sin pasar por el prompt de respuesta, y escribe en ChromaDB y en `index_state.json`.
