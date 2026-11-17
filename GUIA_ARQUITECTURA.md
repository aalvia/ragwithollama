# Guía de arquitectura

Esta guía explica las piezas de AquaRAG con el código que realmente corre, para poder recorrer una pregunta en voz alta.

## Qué es RAG

RAG significa recuperación aumentada por generación. El modelo no contesta desde lo que aprendió en su entrenamiento. Primero se recuperan fragmentos de una base propia y después el modelo redacta usando esos fragmentos.

En AquaRAG la base es `data/documents/`: 20 Markdown sobre camarón blanco, más cualquier PDF, Word, Excel o TXT que se agregue después.

## Qué es un LLM

Un modelo de lenguaje predice el siguiente texto. `qwen2.5:1.5b` es el LLM de este proyecto. Tiene unos 1,5 mil millones de parámetros y pesa cerca de 1 GB. Redacta en español y cabe en una laptop sin VRAM.

No es la fuente de los datos. Si se le pregunta la densidad de siembra sin fragmentos, puede inventar una cifra. Por eso la aplicación solo lo llama cuando ChromaDB devolvió fragmentos por debajo de la distancia máxima.

## Qué es Ollama

Ollama es el programa que carga el modelo y expone `http://127.0.0.1:11434`. AquaRAG no enlaza una librería de inferencia dentro del proceso de Python. Habla por HTTP:

- `GET /api/tags` para saber si el servicio vive y qué modelos hay.
- `POST /api/embed` para los vectores.
- `POST /api/chat` para la respuesta.

El mismo Ollama ya lo usa el proyecto de `G:\mar`, con otro modelo y otro propósito. Aquí se reutiliza el servicio. No se instala un segundo Ollama.

## Qué es Qwen 2.5 en este proyecto

El modelo concreto es `qwen2.5:1.5b`. Se eligió porque ya estaba descargado y porque la demo tiene que correr sin tarjeta de vídeo. `qwen2.5:7b` redacta con más cuidado, y también tarda mucho más en CPU. El cambio, el día que haga falta, es una línea de `.env` y una descarga. El índice de ChromaDB no depende del modelo de respuestas. Depende del modelo de embeddings.

La temperatura está en 0,1 y la respuesta se corta en 700 tokens. Las dos cosas están en `.env`.

## Qué son los embeddings

Un embedding es una lista de números que representa el significado de un texto. Dos textos sobre oxígeno disuelto quedan cerca. Un texto sobre oxígeno y otro sobre la capital de Francia quedan más lejos.

`nomic-embed-text` produce ese vector. Para buscar bien exige un prefijo distinto:

- documentos: `search_document: `
- preguntas: `search_query: `

Eso está en `app/services/embedding_service.py`. Si se omite el prefijo, la búsqueda empeora aunque ChromaDB esté bien configurado. Es una propiedad de este modelo, no de la base vectorial.

## Qué es una base de datos vectorial

Una base vectorial guarda esos números y responde «dame los más parecidos a este». También guarda el texto y los metadatos, porque un vector solo no se puede mostrar como fuente.

AquaRAG guarda, junto a cada vector, el archivo, la ruta, la página si existe, la sección, el número de fragmento, la fecha y el hash del archivo.

## Qué hace ChromaDB

ChromaDB es la base vectorial local. No hay un servidor aparte. `PersistentClient` escribe en `data/chroma_db`. La colección `aquarag` usa distancia coseno: 0 es lo más parecido.

ChromaDB no calcula los embeddings de este proyecto. Si lo hiciera, descargaría su propio modelo. `VectorRepository` inserta vectores que ya llegaron de Ollama y consulta con `query_embeddings`.

Con 213 fragmentos la búsqueda es inmediata. El valor de ChromaDB aquí es la persistencia, el reemplazo de los fragmentos de un archivo cuando ese archivo cambia, y la devolución del metadato que la pantalla muestra como fuente.

## Qué es la recuperación semántica

No es una búsqueda por palabra exacta. La pregunta «¿por qué el oxígeno baja antes del amanecer?» no necesita contener la frase «respiración nocturna» para encontrar ese párrafo. El vector de la pregunta se compara con los vectores de los fragmentos.

Eso también tiene un límite. Con pocos documentos, ChromaDB siempre devuelve algo: los menos lejanos. «Menos lejano» no significa «del tema». Por eso `RagService` descarta distancias mayores a `MAX_DISTANCE` (0,30). Ese número se midió: las preguntas del corpus quedaron entre 0,15 y 0,29, y las preguntas ajenas empezaron cerca de 0,32.

## Qué es el chunking

Un documento entero es demasiado largo para un vector fino y para el contexto del modelo chico. `split_text` lo parte en unos 800 caracteres, con 150 de solape. En Markdown el corte respeta los títulos. Cada fragmento lleva el nombre del archivo y la sección, así que el vector sabe de qué documento habla.

El solape evita perder la frase que justo cae en el borde del corte.

## Recuperación y generación

Son dos pasos distintos.

La recuperación elige fragmentos. La hace `nomic-embed-text` más ChromaDB. No redacta.

La generación redacta. La hace `qwen2.5:1.5b` con esos fragmentos en el prompt. No elige los archivos. Las fuentes de la respuesta salen del paso anterior, aunque el modelo mencione mal un nombre.

Si la recuperación vuelve vacía, no hay generación. Hay un mensaje fijo de información insuficiente.

## Flujo de una consulta

1. El navegador envía `POST /api/chat` con la pregunta y un `session_id`.
2. Si `CONVERSATION_CONTEXT=true`, se leen los turnos previos de esa sesión. Si es `false`, la historia está vacía.
3. Se arma el texto de búsqueda. Sin memoria, es la pregunta. Con memoria, es la pregunta anterior más la actual.
4. Ollama embebe ese texto con el prefijo `search_query: `.
5. ChromaDB devuelve hasta 5 fragmentos.
6. Se descartan los de distancia mayor a 0,30.
7. Si no queda ninguno, se responde el mensaje fijo. No hay llamada al LLM.
8. Si quedan, se construye el prompt y Ollama redacta.
9. La API devuelve la respuesta, las fuentes, los documentos distintos y el tiempo.
10. Si la memoria está encendida, se guardan la pregunta y la respuesta en RAM, con un tope de turnos.

## Diferencia entre RAG y fine-tuning

El fine-tuning modifica los pesos del modelo con ejemplos. Hace falta un conjunto de entrenamiento, tiempo de cómputo y un modelo nuevo cada vez que el protocolo de la finca cambia.

RAG no toca los pesos. Cambia los documentos, se reindexa el archivo modificado y la siguiente pregunta ya ve el texto nuevo. Para protocolos, costos y parámetros que se actualizan, RAG es la pieza que corresponde. Un fine-tuning no sabría citar el archivo ni olvidar un párrafo que se borró.

## Diferencia entre RAG y un agente

Este sistema es un asistente de una sola acción: buscar y responder. No decide llamar herramientas en cadena, no envía correos y no modifica un estanque.

Un agente observa un objetivo, elige pasos y usa herramientas hasta terminarlo. Por ejemplo: detectar oxígeno bajo en un sensor, consultar el protocolo, avisar al jefe de turno y dejar un registro en el ERP. AquaRAG sería una de esas herramientas, la que responde «qué dice el protocolo», no el agente completo.

El historial de la pantalla tampoco lo convierte en agente. Con `CONVERSATION_CONTEXT=true` solo recuerda unos turnos para entender la pregunta siguiente.

## Cómo se integraría con un ERP

Hoy la carpeta `data/documents/` es la fuente. En una operación real, un proceso programado exportaría del ERP los documentos ya autorizados: protocolo de siembra, lista de precios del alimento, ficha del lote, procedimiento de cosecha. Los dejaría en esa carpeta o en una carpeta por empresa, y llamaría a `POST /api/documents/index`.

La respuesta de AquaRAG no escribiría en el ERP por su cuenta. Un módulo posterior podría tomar la respuesta y la fuente, y proponer un movimiento —por ejemplo una nota en la orden de cosecha— que una persona confirma. Esa confirmación es la diferencia entre consultar y ejecutar.

Los permisos tampoco están en esta demo. El servicio escucha solo en `127.0.0.1`. En un ERP, cada consulta llevaría el usuario y la finca, y el índice estaría partido para que una empresa no recupere documentos de otra. ChromaDB admite un filtro por metadato. El metadato `source_path` ya existe. Faltaría uno de `empresa` o `finca`, cargado al indexar.

## Límites de esta arquitectura

- El modelo de 1,5B resume bien un fragmento claro y se equivoca si el fragmento es ambiguo. Las fuentes permiten ver el original.
- La memoria de conversación es RAM del proceso. Reiniciar la borra.
- No hay usuarios ni contraseñas.
- No hay OCR para PDF escaneados.
- El umbral 0,30 está calibrado con estos 20 documentos. Un corpus distinto se vuelve a medir.
