const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const questionInput = document.querySelector("#question");
const sendButton = document.querySelector("#send-button");
const indexButton = document.querySelector("#index-button");
const refreshButton = document.querySelector("#refresh-button");
const healthButton = document.querySelector("#health-button");
const panelMessage = document.querySelector("#panel-message");

function sessionId() {
  const key = "aquarag_session";
  let value = sessionStorage.getItem(key);
  if (!value) {
    value = crypto.randomUUID();
    sessionStorage.setItem(key, value);
  }
  return value;
}

function setPanelMessage(text, isError) {
  panelMessage.textContent = text || "";
  panelMessage.classList.toggle("error", Boolean(isError));
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "La solicitud no se completó.");
  }
  return payload;
}

function addBubble(role, text) {
  const article = document.createElement("article");
  article.className = `bubble ${role}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  article.appendChild(paragraph);
  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function addSources(article, sources) {
  if (!sources || sources.length === 0) {
    return;
  }
  const list = document.createElement("div");
  list.className = "sources";
  sources.forEach((source) => {
    const block = document.createElement("div");
    block.className = "source";
    const title = document.createElement("strong");
    const page = source.page ? `, página ${source.page}` : "";
    title.textContent = `${source.document}${page}`;
    const meta = document.createElement("div");
    const heading = source.heading ? `${source.heading} · ` : "";
    meta.textContent = `${heading}Fragmento ${source.chunk_id} · distancia ${source.distance}`;
    const excerpt = document.createElement("p");
    excerpt.textContent = source.excerpt;
    block.append(title, meta, excerpt);
    list.appendChild(block);
  });
  article.appendChild(list);
}

async function sendQuestion(question) {
  const pending = addBubble("assistant pending", "Consultando documentos y redactando la respuesta…");
  sendButton.disabled = true;
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, session_id: sessionId() }),
    });
    const payload = await readJson(response);
    pending.remove();
    const article = addBubble("assistant", payload.answer);
    addSources(article, payload.sources);
  } catch (error) {
    pending.remove();
    addBubble("assistant", error.message);
  } finally {
    sendButton.disabled = false;
    questionInput.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = questionInput.value.trim();
  if (!question) {
    return;
  }
  addBubble("user", question);
  questionInput.value = "";
  sendQuestion(question);
});

questionInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

function statusLabel(status) {
  if (status === "indexed") return "Indexado";
  if (status === "modified") return "Modificado";
  return "Pendiente";
}

function renderDocuments(documents) {
  const list = document.querySelector("#document-list");
  list.replaceChildren();
  documents.forEach((documentItem) => {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = documentItem.name;
    const status = document.createElement("span");
    status.className = `status-${documentItem.status}`;
    status.textContent = statusLabel(documentItem.status);
    item.append(name, status);
    list.appendChild(item);
  });
}

async function refreshInfo() {
  const [statsResponse, documentsResponse] = await Promise.all([
    fetch("/api/documents/stats"),
    fetch("/api/documents"),
  ]);
  const stats = await readJson(statsResponse);
  const documents = await readJson(documentsResponse);
  document.querySelector("#doc-count").textContent = String(stats.documents);
  document.querySelector("#chunk-count").textContent = String(stats.chunks);
  document.querySelector("#ollama-status").textContent = stats.ollama_status;
  document.querySelector("#model-name").textContent = stats.llm_model;
  document.querySelector("#index-time").textContent = stats.last_indexed_at
    ? `Última indexación: ${stats.last_indexed_at}`
    : "Última indexación: todavía no hay";
  document.querySelector("#context-badge").textContent = stats.conversation_context
    ? "Contexto de conversación: activo"
    : "Contexto de conversación: apagado";
  renderDocuments(documents.documents);
}

async function refreshHealth() {
  const response = await fetch("/api/health");
  const health = await readJson(response);
  const text = [
    `Estado: ${health.status}`,
    `Ollama: ${health.ollama}`,
    `LLM ${health.llm_model}: ${health.llm_available ? "disponible" : "no disponible"}`,
    `Embeddings ${health.embedding_model}: ${health.embedding_available ? "disponible" : "no disponible"}`,
    `ChromaDB: ${health.chromadb}`,
    `Contexto: ${health.conversation_context ? "activo" : "apagado"}`,
  ].join(" · ");
  setPanelMessage(text, health.status !== "ok");
}

indexButton.addEventListener("click", async () => {
  indexButton.disabled = true;
  setPanelMessage("Indexando documentos. La primera vez puede tardar varios minutos.");
  try {
    const response = await fetch("/api/documents/index", { method: "POST" });
    const report = await readJson(response);
    const summary = `Nuevos ${report.added.length}, modificados ${report.updated.length}, sin cambios ${report.unchanged.length}, fragmentos escritos ${report.chunks_written}.`;
    setPanelMessage(report.errors.length ? `${summary} Errores: ${report.errors.join(" | ")}` : summary, report.errors.length > 0);
    await refreshInfo();
  } catch (error) {
    setPanelMessage(error.message, true);
  } finally {
    indexButton.disabled = false;
  }
});

refreshButton.addEventListener("click", async () => {
  try {
    await refreshInfo();
    setPanelMessage("Información actualizada.");
  } catch (error) {
    setPanelMessage(error.message, true);
  }
});

healthButton.addEventListener("click", () => {
  refreshHealth().catch((error) => setPanelMessage(error.message, true));
});

refreshInfo().catch((error) => setPanelMessage(error.message, true));
refreshHealth().catch(() => {});
