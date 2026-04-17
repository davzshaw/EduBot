(function () {
  const views = {
    home: document.getElementById("view-home"),
    chat: document.getElementById("view-chat"),
    subjects: document.getElementById("view-subjects"),
  };

  const navBtns = document.querySelectorAll("[data-nav]");
  const chatLog = document.getElementById("chat-log");
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const sendBtn = document.getElementById("btn-send");
  const resetChatBtn = document.getElementById("btn-reset-chat");
  const subjectLabel = document.getElementById("subject-label");
  const badgeDemo = document.getElementById("badge-demo");
  const modal = document.getElementById("info-modal");
  const modalOpeners = document.querySelectorAll("[data-open-info]");
  const modalClose = document.getElementById("modal-close");

  let currentSubject = null;

  function showView(name) {
    Object.keys(views).forEach((k) => {
      views[k].classList.toggle("is-active", k === name);
    });
    navBtns.forEach((b) => {
      b.classList.toggle("is-active", b.getAttribute("data-nav") === name);
    });
    if (name === "chat") {
      ensureWelcome();
    }
  }

  function fmtTime(d) {
    return d.toLocaleTimeString("es-CO", { hour: "2-digit", minute: "2-digit" });
  }

  function appendBubble(role, text, extraMeta) {
    const row = document.createElement("div");
    row.className = "msg-row " + (role === "user" ? "user" : "bot");
    const bubble = document.createElement("div");
    bubble.className = "bubble " + (role === "user" ? "user" : "bot");

    const body = document.createElement("div");
    body.style.margin = "0";
    body.textContent = text;
    bubble.appendChild(body);

    const meta = document.createElement("span");
    meta.className = "msg-meta " + (role === "user" ? "user" : "");
    const t = fmtTime(new Date());
    if (role === "user") {
      meta.innerHTML =
        t + '<span class="checks" aria-hidden="true"> ✓✓</span>';
    } else {
      meta.textContent = t + (extraMeta ? " · " + extraMeta : "");
    }
    bubble.appendChild(meta);
    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function showPending() {
    const row = document.createElement("div");
    row.className = "msg-row bot";
    row.id = "pending-row";
    const inner = document.createElement("div");
    inner.className = "pending-row";
    inner.setAttribute("role", "status");
    inner.innerHTML =
      '<span class="spinner" aria-hidden="true"></span> EduBot está pensando…';
    row.appendChild(inner);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function removePending() {
    document.getElementById("pending-row")?.remove();
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    chatInput.disabled = busy;
    if (resetChatBtn) resetChatBtn.disabled = busy;
  }

  function ensureWelcome() {
    if (chatLog.querySelector(".msg-row")) return;
    const pill = document.querySelector(".date-pill");
    if (pill) pill.style.display = "block";
    appendBubble(
      "bot",
      "¡Hola! Soy EduBot. Estoy aquí para orientarte en tus dudas de estudio (sin darte la tarea hecha). ¿En qué te puedo ayudar a aprender hoy?"
    );
  }

  async function refreshStatus() {
    try {
      const r = await fetch("/api/status");
      const data = await r.json();
      if (badgeDemo) {
        badgeDemo.style.display = data.use_llm ? "none" : "block";
      }
      if (data.subject) {
        currentSubject = data.subject;
        updateSubjectUi();
      }
    } catch (_) {
      /* silencio */
    }
  }

  function updateSubjectUi() {
    if (!subjectLabel) return;
    if (currentSubject) {
      subjectLabel.innerHTML =
        '<span>Materia: ' + escapeHtml(currentSubject) + "</span>";
      subjectLabel.style.display = "block";
    } else {
      subjectLabel.textContent = "";
      subjectLabel.style.display = "none";
    }
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  navBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      showView(btn.getAttribute("data-nav"));
    });
  });

  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = "";
    appendBubble("user", text);
    showPending();
    setBusy(true);
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, subject: currentSubject }),
      });
      const data = await r.json();
      removePending();
      if (!r.ok) {
        appendBubble("bot", data.error || "No se pudo obtener respuesta.");
      } else {
        appendBubble("bot", data.reply, data.mode === "mock" ? "demo" : "");
      }
    } catch (err) {
      removePending();
      appendBubble("bot", "Error de red: " + String(err));
    }
    setBusy(false);
    chatInput.focus();
  });

  document.querySelectorAll("[data-subject]").forEach((el) => {
    el.addEventListener("click", async () => {
      const subj = el.getAttribute("data-subject") || "";
      currentSubject = subj;
      try {
        await fetch("/api/session/subject", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subject: subj }),
        });
      } catch (_) {}
      updateSubjectUi();
      showView("chat");
      chatInput.focus();
    });
  });

  if (resetChatBtn) {
    resetChatBtn.addEventListener("click", async () => {
      await fetch("/api/reset", { method: "POST" });
      chatLog.innerHTML = "";
      ensureWelcome();
    });
  }

  function openModal() {
    modal.classList.add("is-open");
  }
  function closeModal() {
    modal.classList.remove("is-open");
  }

  modalOpeners.forEach((b) => b.addEventListener("click", openModal));
  if (modalClose) modalClose.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  refreshStatus();
  showView("home");
})();
