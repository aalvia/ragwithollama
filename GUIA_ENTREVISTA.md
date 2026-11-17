# Guía de entrevista

Respuestas para defender AquaRAG como líder de automatización e inteligencia artificial. Cada respuesta describe el sistema que está en este repositorio.

## ¿Qué es RAG?

Es una arquitectura de dos pasos. Primero se recuperan fragmentos de documentos propios. Después un modelo redacta usando solo esos fragmentos. En AquaRAG los documentos están en `data/documents/`, los vectores en ChromaDB y la redacción la hace `qwen2.5:1.5b` a través de Ollama. Si la recuperación no encuentra nada por debajo de la distancia 0,30, el modelo no se llama. Hay un mensaje fijo. Eso evita que un modelo pequeño conteste como si hubiera leído un archivo.

## ¿Por qué utilizar ChromaDB?

Porque los embeddings tienen que persistir y hay que buscar los vecinos junto con el nombre del archivo. ChromaDB corre dentro del proceso de Python, escribe en `data/chroma_db` y no pide otro servidor. Con 213 fragmentos la matemática es pequeña. Lo que no quise programar a mano es el reemplazo de los fragmentos cuando un archivo cambia, el borrado cuando el archivo desaparece y la supervivencia al reinicio.

ChromaDB no embebe en este proyecto. Si lo hiciera con su función por defecto, descargaría otro modelo. Los vectores llegan desde Ollama.

## ¿Qué son los embeddings y cómo funcionan aquí?

Un embedding es una lista de números que acerca textos de significado parecido. `nomic-embed-text` lo calcula. Este modelo pide un prefijo: `search_document: ` para lo que se indexa y `search_query: ` para la pregunta. El prefijo no se guarda en el texto que ve el usuario. Solo entra al vector.

Medí las distancias en coseno con el corpus real. Una pregunta de densidad de siembra cayó en 0,181 sobre `densidad_de_siembra.md`. La capital de Francia cayó en 0,365 sobre un documento que no habla de eso, y el filtro la descartó.

## ¿Por qué Qwen 2.5 de 1,5B y no uno de 7B?

Porque la laptop donde se va a demostrar no tiene VRAM. `qwen2.5:1.5b` ya estaba en el Ollama de esta máquina, pesa cerca de 1 GB y responde en pocos segundos. `qwen2.5:7b` redacta mejor y en CPU se vuelve lento para una demo en vivo. El modelo no está escrito en el código de las rutas. Está en `OLLAMA_MODEL`. Subir a 7B es cambiar la variable y descargar el modelo. El índice no se rehace, porque el embedding sigue siendo `nomic-embed-text`.

El modelo chico se compensa con un control fuera del modelo: sin fragmentos relevantes no hay generación.

## ¿Qué hace Ollama?

Carga el modelo en la máquina y expone HTTP en el puerto 11434. AquaRAG usa el Ollama que ya estaba instalado, versión 0.40.16, el mismo servicio del otro proyecto local. No hay clave ni pago por token. Python solo envía JSON.

## ¿Cómo evitar alucinaciones?

Con varias barreras, no con una frase en el prompt.

1. El prompt exige cifras y procedimientos solo de los fragmentos, y prohíbe estudios o normas inventadas.
2. La temperatura está en 0,1.
3. Si la mejor distancia supera 0,30, el modelo no se llama.
4. Las fuentes que muestra la pantalla salen de ChromaDB, no del párrafo que redactó el modelo.
5. Los documentos declaran que los rangos son orientativos y que una mancha no es un diagnóstico. El prompt repite esa regla.

Aun así, 1,5B puede parafrasear mal un fragmento correcto. Por eso la fuente va debajo de la respuesta y se puede leer el original.

## ¿Cómo controlar permisos?

Esta demo no tiene login. Escucha solo en `127.0.0.1`, así que otra máquina de la red no llega. Los archivos que indexa son los que están dentro de `data/documents/`. La ruta se resuelve con `relative_to`, de modo que un archivo fuera de esa carpeta no entra.

En un ERP el siguiente paso es un índice por empresa. Al indexar se guarda un metadato `empresa` y la consulta filtra por la empresa del usuario. ChromaDB ya filtra por metadato. Hoy el metadato que existe es el archivo. Separar empresas es agregar ese campo, no cambiar de arquitectura. Quien no deba ver costos no debería tener esos archivos en el mismo índice que quien solo ve el protocolo sanitario.

## ¿Cómo integrar RAG con un ERP?

El ERP sigue siendo el sistema que registra siembra, alimento, cosecha y factura. AquaRAG no lo reemplaza. Un job exporta al directorio documental los procedimientos y las fichas que el negocio ya aprobó, y llama a `POST /api/documents/index`. El índice solo toca lo nuevo o lo modificado, porque compara el hash del archivo.

La respuesta vuelve con fuentes. Un analista la usa para decidir. Si más adelante un agente propone crear una nota en la orden de producción, esa escritura pasa por una confirmación humana y por el permiso del ERP. Consultar un protocolo y ejecutar un movimiento son pasos distintos.

## ¿Cómo automatizar procesos?

La automatización de este proyecto es concreta: detectar archivos nuevos, modificados y borrados, extraer el texto, partirlo, embeberlo y actualizar ChromaDB sin repetir lo que no cambió. La segunda corrida de los 20 documentos reescribió 0 fragmentos.

Alrededor se puede programar esa indexación cada noche, avisar si Ollama no responde en `/api/health`, y dejar la pregunta frecuente —oxígeno, FCR, densidad— disponible para el equipo de campo sin abrir el manual completo. Eso es automatización de conocimiento. Todavía no es automatización de la compuerta ni del alimento.

## ¿Qué diferencia hay entre un chatbot y un agente?

Un chatbot de este tipo responde un mensaje. AquaRAG es eso, con recuperación de documentos. No elige herramientas ni encadena acciones.

Un agente recibe un objetivo, decide pasos y usa herramientas. Podría leer un sensor, preguntarle a AquaRAG cuál es el umbral orientativo de oxígeno, y después abrir un aviso en el ERP. AquaRAG sería la herramienta de consulta. Convertirlo en agente sin una acción autorizada solo agrega pasos que el modelo de 1,5B no debe ejecutar solo.

El modo `CONVERSATION_CONTEXT=true` no lo vuelve agente. Solo recuerda hasta 4 turnos en memoria para entender «¿y en postlarvas?». Al cerrar el proceso, esa memoria desaparece.

## ¿Cómo medir la calidad de la recuperación?

No basta con mirar si la respuesta «suena bien». Se mira la distancia y el archivo.

En este corpus armé preguntas de oxígeno, FCR, densidad, mancha blanca, bioseguridad, cosecha, biomasa y salinidad, y preguntas ajenas. Las del tema quedaron entre 0,15 y 0,29, casi siempre en el archivo correcto. Las ajenas empezaron en 0,32. El umbral 0,30 sale de esa medición.

Las pruebas de integración cubren el caso positivo y el negativo con Ollama real. Si se agregan documentos, hay que repetir la medición. Un umbral copiado de otro corpus deja pasar ruido o deja mudas las preguntas buenas.

También miro el segundo puesto. A veces el mejor fragmento es el correcto y el tercero es de otro archivo, todavía bajo el umbral. El modelo recibe ese ruido. Si empieza a mezclar temas, bajo `TOP_K` o el umbral.

## ¿Qué haría si aumenta el volumen documental?

Primero mediría de nuevo el umbral y el tiempo de indexación. ChromaDB local aguanta bastante más que 213 fragmentos en una sola máquina. Cuando el corpus sea de muchas fincas, separaría colecciones o filtraría por metadato de empresa, para no buscar en documentos que el usuario no puede ver.

Si la indexación nocturna ya no cabe en la ventana, embebería por lotes y por archivo modificado, que es lo que el hash ya permite. No reindexaría todo cada noche.

El modelo de embeddings se puede cambiar por uno mejor en español. Hay que borrar `data/chroma_db` y reindexar, porque los vectores viejos no se comparan con los nuevos. El modelo de respuestas se cambia sin reindexar.

## ¿Cómo escalar a producción?

Esta forma es de una máquina y un usuario. Para producción mantendría el mismo flujo y cambiaría el empaque:

- El servicio deja de escuchar solo en localhost y queda detrás de la red de la empresa, con autenticación.
- Un índice por empresa, con filtro obligatorio.
- La carpeta documental sale de un almacenamiento controlado, no de una copia en el escritorio.
- La salud de Ollama entra al monitoreo. Si el modelo no está, el chat falla con 503 y no inventa.
- El modelo de respuestas puede subir de tamaño en un servidor con GPU. El contrato de la API no cambia.

No metería Kubernetes para esta carga. Primero un proceso, un disco y un control de acceso. La complejidad se agrega cuando hay varias empresas y un requisito de disponibilidad, no antes.

## ¿Cómo proteger documentos confidenciales?

Hoy la protección es física y de red: los archivos están en esta PC y la API no se publica. Eso no alcanza si el mismo Windows lo usan varias personas.

En serio: los documentos viven donde el ERP ya controla el acceso. Se indexan solo los que ese perfil puede leer. El disco del índice se cifra. Los logs no guardan el texto completo de un contrato. `.env` no lleva contraseñas. Las respuestas muestran un extracto. Quien no debe ver costos no tiene el archivo de costos en su índice.

Borrar un documento del disco no basta: la indexación siguiente tiene que borrar sus vectores. `plan_index_actions` ya marca como eliminado un archivo que desapareció.

## ¿Cómo medir el ROI?

No lo mediría por cantidad de mensajes. Lo mediría por tiempo de búsqueda y por errores evitados.

Antes: un supervisor abre varios manuales para responder cuántos animales por metro cuadrado autoriza el protocolo y qué fórmula de FCR usa la empresa. Después: la misma pregunta devuelve el párrafo y el archivo en segundos. El ahorro es ese tiempo, multiplicado por las consultas repetidas del turno.

El segundo número es el costo de una decisión tomada con una cifra inventada: una densidad copiada de otra finca, un FCR calculado con la supervivencia equivocada. RAG no elimina ese riesgo. Lo reduce si la gente lee la fuente. Si nadie abre la fuente, el ROI no aparece.

Un piloto serio anota, durante un mes, cuántas preguntas se respondieron con fuente, cuántas quedaron sin información y cuántas veces la fuente estaba desactualizada. Esa última cifra dice si el problema es el modelo o el proceso de publicar documentos.

## ¿Qué limitaciones tiene una arquitectura local?

- El modelo cabe en la laptop y, a cambio, redacta peor que uno grande.
- Todo el conocimiento útil tiene que estar en los archivos. Lo que no se indexó no existe para el sistema.
- El umbral de distancia hay que medirlo. No viaja solo de un corpus a otro.
- No hay alta disponibilidad. Si se apaga la PC, se apaga el asistente.
- La memoria de conversación no se comparte entre usuarios ni sobrevive a un reinicio.
- No diagnostica enfermedades ni calcula la dosis de nada. Los documentos lo dicen y el prompt lo repite. Igual hay que decirlo en la entrevista: esto es material educativo pendiente de validación técnica.

La limitación que defiendo con más claridad es esta: un modelo local pequeño es suficiente cuando la recuperación es buena y la aplicación se niega a contestar sin fragmentos. No es suficiente si se le pide recordar la camaronicultura por su cuenta.
