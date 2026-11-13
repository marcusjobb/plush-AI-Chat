(() => {
  const chat = document.getElementById("chat");

  // Rulla alltid ner när något läggs till i chatten: svar, systemrader och väntetexten.
  new MutationObserver(() => {
    requestAnimationFrame(() => {
      chat.scrollTop = chat.scrollHeight;
    });
  }).observe(chat, { childList: true });
  const form = document.getElementById("composer");
  const input = document.getElementById("input");
  const sendBtn = document.getElementById("send");
  const assistantsEl = document.getElementById("assistants");
  const select = document.getElementById("session");
  const newBtn = document.getElementById("new-session");
  const compactBtn = document.getElementById("compact");

  const SELECTED_KEY = "multiAssistant.session";
  let assistants = [];
  let currentId = null;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Något gick fel.");
    return data;
  }

  function addMessage(speaker, content) {
    const row = el("div", "msg");
    if (speaker === "Du") {
      row.classList.add("user");
      const bubble = el("div", "bubble md");
      bubble.innerHTML = window.renderMarkdown(content);
      row.append(bubble);
    } else if (speaker === "system") {
      row.classList.add("system");
      row.append(el("div", "bubble", content));
    } else {
      row.classList.add("assistant");
      const info = assistants.find((a) => a.name === speaker);
      row.append(el("div", "avatar", speaker.charAt(0).toUpperCase()));
      const body = el("div", "bubble");
      const label = el("div", "name", speaker);
      if (info) label.append(el("span", "model", info.model));
      const text = el("div", "md");
      text.innerHTML = window.renderMarkdown(content);
      body.append(label, text);
      row.append(body);
    }
    chat.append(row);
    row.scrollIntoView({ block: "end" });
    return row;
  }

  function showError(text) {
    addMessage("system", text);
  }

  let selected; // null = alla, annars listan med valda namn. Förval: första assistenten.

  function renderAssistants() {
    if (selected === undefined) {
      selected = assistants.length ? [assistants[0].name] : null;
    }
    assistantsEl.replaceChildren(
      ...assistants.map((a) => el("span", null, `${a.name} (${a.model})`))
    );
    renderTargets();
  }

  function renderTargets() {
    const box = document.getElementById("targets");
    const options = [
      { label: "Alla", value: null },
      ...assistants.map((a) => ({ label: a.name, value: [a.name] })),
    ];
    box.replaceChildren(
      ...options.map((opt) => {
        const btn = el("button", "pill target", opt.label);
        btn.type = "button";
        const active = JSON.stringify(opt.value) === JSON.stringify(selected);
        btn.classList.toggle("active", active);
        btn.setAttribute("aria-pressed", String(active));
        btn.addEventListener("click", () => {
          selected = opt.value;
          renderTargets();
        });
        return btn;
      })
    );
  }

  async function loadSessions(selectId) {
    const data = await api("/api/sessions");
    select.replaceChildren(
      ...data.sessions.map((s) => {
        const opt = el("option", null, s.title);
        opt.value = s.id;
        return opt;
      })
    );
    if (selectId && data.sessions.some((s) => s.id === selectId)) {
      select.value = selectId;
    }
    return data.sessions;
  }

  async function openSession(id) {
    currentId = id;
    chat.replaceChildren();
    try {
      const data = await api(`/api/sessions/${id}`);
      data.messages.forEach((m) => addMessage(m.speaker, m.content));
    } catch (err) {
      showError(err.message);
    }
    try {
      localStorage.setItem(SELECTED_KEY, id);
    } catch (_) {
      /* privat läge eller blockerad lagring: ingen fara */
    }
    loadDocuments();
  }

  async function createSession() {
    const data = await api("/api/sessions", { method: "POST" });
    await loadSessions(data.id);
    await openSession(data.id);
    input.focus();
  }

  async function ensureSession() {
    if (currentId) return currentId;
    await createSession();
    return currentId;
  }

  async function send(text) {
    if (sendBtn.disabled) return;
    sendBtn.disabled = true;
    let id;
    try {
      id = await ensureSession();
    } catch (err) {
      sendBtn.disabled = false;
      showError(err.message);
      return;
    }
    const pending = el("div", "msg assistant");
    pending.append(el("div", "bubble typing", "Assistenterna tänker…"));
    chat.append(pending);
    try {
      const data = await api(`/api/sessions/${id}/message`, {
        method: "POST",
        body: JSON.stringify({ text, selected }),
      });
      pending.remove();
      // Svaret hör till sessionen den skickades i. Visa det bara om användaren står kvar där.
      if (currentId === id) {
        data.messages.forEach((m) => addMessage(m.speaker, m.content));
      }
      await loadSessions(currentId);
      loadDocuments();
    } catch (err) {
      pending.remove();
      if (currentId === id) showError(err.message);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  async function compact() {
    if (!currentId) return;
    compactBtn.disabled = true;
    const pending = el("div", "msg assistant");
    pending.append(el("div", "bubble typing", "Sammanfattar samtalet…"));
    chat.append(pending);
    try {
      const data = await api(`/api/sessions/${currentId}/compact`, { method: "POST" });
      pending.remove();
      addMessage(data.message.speaker, data.message.content);
    } catch (err) {
      pending.remove();
      showError(err.message);
    } finally {
      compactBtn.disabled = false;
    }
  }

  const uploadInput = document.getElementById("upload");

  async function uploadFile(file) {
    const sessionId = await ensureSession();
    const form = new FormData();
    form.append("file", file);
    form.append("session_id", sessionId);
    try {
      const res = await fetch("/api/documents", { method: "POST", body: form });
      if (!res.ok) {
        const data = await res.json();
        showError(data.error || "Uppladdningen misslyckades.");
      } else {
        loadDocuments();
      }
    } catch (err) {
      showError("Kunde inte ladda upp filen.");
    } finally {
      uploadInput.value = "";
    }
  }

  uploadInput.addEventListener("change", () => {
    const file = uploadInput.files[0];
    if (file) uploadFile(file);
  });

  const renameBtn = document.getElementById("rename");

  renameBtn.addEventListener("click", async () => {
    if (!currentId) return;
    const current = select.options[select.selectedIndex]?.text || "";
    const title = window.prompt("Nytt namn på sessionen:", current);
    if (title === null || !title.trim()) return;
    try {
      await api(`/api/sessions/${currentId}/title`, {
        method: "POST",
        body: JSON.stringify({ title: title.trim() }),
      });
      await loadSessions(currentId);
    } catch (err) {
      showError(err.message);
    }
  });

  const docList = document.getElementById("documents");
  const docEmpty = document.getElementById("doc-empty");
  const sidebar = document.getElementById("sidebar");
  const unloadBtn = document.getElementById("unload");
  const toggleBtn = document.getElementById("toggle-sidebar");

  async function loadDocuments() {
    const query = currentId ? `?session_id=${encodeURIComponent(currentId)}` : "";
    try {
      const data = await api(`/api/documents${query}`);
      renderDocuments(data.documents, data.current);
    } catch (err) {
      // Dokumentlistan är en extra; chatten fungerar utan den.
    }
  }

  function renderDocuments(names, current) {
    docList.replaceChildren(
      ...names.map((name) => {
        const item = el("li");
        const btn = el("button", "doc-item" + (name === current ? " active" : ""), name);
        btn.type = "button";
        btn.title = name === current ? "Aktiv i historiken" : "Ladda in i historiken";
        btn.addEventListener("click", () => openDocument(name));
        item.append(btn);
        return item;
      })
    );
    docEmpty.hidden = names.length > 0;
    unloadBtn.hidden = !current;
  }

  function loadDocument(name) {
    sidebar.classList.remove("open");
    send(`/dokument ${name}`);
  }

  const modal = document.getElementById("doc-modal");
  const docTitle = document.getElementById("doc-title");
  const docText = document.getElementById("doc-text");
  const tabOriginal = document.getElementById("tab-original");
  const tabCompact = document.getElementById("tab-compact");
  let openDoc = null;

  function showDocVersion(which) {
    tabOriginal.classList.toggle("active", which === "original");
    tabCompact.classList.toggle("active", which === "compact");
    docText.textContent = openDoc[which];
  }

  const docEditor = document.getElementById("doc-editor");
  const editBtn = document.getElementById("doc-edit");
  const saveCopyBtn = document.getElementById("doc-save-copy");
  const cancelEditBtn = document.getElementById("doc-cancel-edit");

  function setEditing(on) {
    docEditor.hidden = !on;
    docText.hidden = on;
    editBtn.hidden = on;
    saveCopyBtn.hidden = !on;
    cancelEditBtn.hidden = !on;
    if (on && openDoc) {
      docEditor.value = openDoc.original;
      docEditor.focus();
    }
  }

  function closeDocument() {
    setEditing(false);
    modal.hidden = true;
    openDoc = null;
  }

  async function openDocument(name) {
    let data;
    try {
      data = await api(`/api/documents/${encodeURIComponent(name)}`);
    } catch (err) {
      showError(err.message);
      return;
    }
    openDoc = data;
    sidebar.classList.remove("open");
    docTitle.textContent = name;
    showDocVersion("original");
    modal.hidden = false;
  }

  tabOriginal.addEventListener("click", () => {
    if (!openDoc) return;
    setEditing(false);
    showDocVersion("original");
  });
  tabCompact.addEventListener("click", () => {
    if (!openDoc) return;
    setEditing(false);
    showDocVersion("compact");
  });
  editBtn.addEventListener("click", () => openDoc && setEditing(true));
  cancelEditBtn.addEventListener("click", () => setEditing(false));
  saveCopyBtn.addEventListener("click", async () => {
    if (!openDoc) return;
    const dot = openDoc.name.lastIndexOf(".");
    const stem = dot > 0 ? openDoc.name.slice(0, dot) : openDoc.name;
    const ext = dot > 0 ? openDoc.name.slice(dot) : "";
    const name = window.prompt("Namn på den nya filen:", `${stem}-redigerad${ext}`);
    if (!name || !name.trim()) return;
    try {
      await api("/api/documents/save", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), text: docEditor.value }),
      });
      closeDocument();
      await loadDocuments();
    } catch (err) {
      showError(err.message);
    }
  });
  document.getElementById("doc-close").addEventListener("click", closeDocument);
  document.getElementById("doc-load").addEventListener("click", () => {
    if (!openDoc) return;
    const name = openDoc.name;
    closeDocument();
    loadDocument(name);
  });
  document.getElementById("doc-load-original").addEventListener("click", () => {
    if (!openDoc) return;
    const name = openDoc.name;
    closeDocument();
    sidebar.classList.remove("open");
    send(`/original ${name}`);
  });
  document.getElementById("doc-delete").addEventListener("click", async () => {
    if (!openDoc) return;
    const name = openDoc.name;
    if (!window.confirm(`Flytta ${name} till papperskorgen?`)) return;
    const query = currentId ? `?session_id=${encodeURIComponent(currentId)}` : "";
    try {
      await api(`/api/documents/${encodeURIComponent(name)}${query}`, { method: "DELETE" });
      closeDocument();
      await loadDocuments();
    } catch (err) {
      showError(err.message);
    }
  });
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeDocument();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeDocument();
  });

  unloadBtn.addEventListener("click", () => send("/dokument av"));
  toggleBtn.addEventListener("click", () => sidebar.classList.toggle("open"));

  select.addEventListener("change", () => openSession(select.value));
  newBtn.addEventListener("click", () => createSession().catch((e) => showError(e.message)));
  compactBtn.addEventListener("click", compact);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (sendBtn.disabled) return;
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    autosize();
    send(text);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  function autosize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 180) + "px";
  }
  input.addEventListener("input", autosize);

  async function start() {
    const info = await api("/api/info");
    assistants = info.assistants;
    renderAssistants();

    let remembered = null;
    try {
      remembered = localStorage.getItem(SELECTED_KEY);
    } catch (_) {
      remembered = null;
    }
    const sessions = await loadSessions(remembered);
    if (sessions.length === 0) {
      await createSession();
    } else {
      await openSession(select.value);
    }
  }

  start().catch(() => showError("Kunde inte starta chatten. Kontrollera att servern körs."));
})();
