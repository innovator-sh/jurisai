// Chat page logic. Depends on auth.js (apiFetch/ensureAuthenticated),
// marked + DOMPurify (vendored locally, loaded before this file -- see
// index.html's {% block scripts %}), and base.js (sidebar nav/theme, loaded
// even earlier). No inline <script> or innerHTML-of-raw-text anywhere in
// this file -- every render of model or user-controlled text goes through
// renderSafeMarkdown() or textContent. This is the fix for D009 (LLM output
// into innerHTML unescaped) and D010 (session replay into innerHTML
// unescaped); D011 (error messages into innerHTML unescaped) is fixed the
// same way below -- every error path uses textContent, never markdown.

document.addEventListener("DOMContentLoaded", async () => {
  const authed = await ensureAuthenticated();
  if (!authed) return;

  const chatContainer = document.getElementById("chatContainer");
  const userInput = document.getElementById("userInput");
  const sendButton = document.getElementById("sendButton");
  const abortButton = document.getElementById("abortButton");
  const micButton = document.getElementById("micButton");
  const scrollToBottomBtn = document.getElementById("scrollToBottom");
  const sessionListContainer = document.getElementById("sessionListContainer");
  const sessionList = document.getElementById("sessionList");
  const actionsRow = document.getElementById("actionsRow");
  const corpusToggle = document.getElementById("corpusToggle");

  // ---------- Per-role disclaimer (Sprint 6, DPDP/consumer-safety item) ----------
  // Role is self-declared at signup and only selects how loudly we say "not
  // legal advice" -- it never gates access. Anything unknown or unreachable
  // falls back to the strictest (citizen) wording.
  const DISCLAIMERS = {
    citizen: {
      strong: true,
      footer:
        "JurisAI is not a lawyer and this is not legal advice. Answers are general " +
        "information and may be incomplete or out of date. For your situation, consult a " +
        "qualified lawyer. Free legal aid: NALSA helpline 15100.",
      answer:
        "Not legal advice. This is general information only — please consult a qualified " +
        "lawyer before acting on it.",
    },
    lawyer: {
      strong: false,
      footer:
        "JurisAI is a research aid, not legal advice. Verify every section against the " +
        "official text before relying on it.",
    },
    police: {
      strong: false,
      footer:
        "JurisAI is a reference aid, not legal advice. Verify every section against the " +
        "official text and consult your legal adviser before acting.",
    },
  };
  let disclaimer = DISCLAIMERS.citizen;
  try {
    const meRes = await apiFetch("/api/auth/me");
    if (meRes.ok) {
      const me = await meRes.json();
      disclaimer = DISCLAIMERS[me.role] || DISCLAIMERS.citizen;
    }
  } catch {
    // Network blip: stay on the strictest wording.
  }
  const disclaimerEl = document.getElementById("disclaimer");
  disclaimerEl.textContent = disclaimer.footer; // textContent only
  disclaimerEl.classList.toggle("disclaimer-strong", disclaimer.strong);

  let currentSessionId = null;
  let abortController = null;
  const CORPUS_KEY = "defaultCorpusMode"; // "" | "ipc" | "bns" -- written by settings.js

  // ---------- Safe rendering ----------

  function renderSafeMarkdown(container, rawText) {
    const html = DOMPurify.sanitize(marked.parse(rawText), {
      ALLOWED_TAGS: [
        "p", "br", "strong", "em", "ul", "ol", "li", "blockquote",
        "code", "pre", "a", "h1", "h2", "h3", "h4", "table", "thead",
        "tbody", "tr", "th", "td",
      ],
      ALLOWED_ATTR: ["href"],
    });
    container.innerHTML = html;
    container.querySelectorAll("a").forEach((a) => {
      a.setAttribute("rel", "noopener noreferrer");
      a.setAttribute("target", "_blank");
    });
  }

  function scrollChatToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }

  function toggleScrollButton() {
    const nearBottom =
      chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < 100;
    scrollToBottomBtn.style.display = nearBottom ? "none" : "flex";
  }

  function addMessage({ isUser, text, markdown = false }) {
    const messageDiv = document.createElement("div");
    messageDiv.className = `message ${isUser ? "user-message" : "bot-message"}`;

    const header = document.createElement("div");
    header.className = "message-header";

    const avatar = document.createElement("div");
    avatar.className = `message-avatar ${isUser ? "user-avatar" : "bot-avatar"}`;
    avatar.textContent = isUser ? "U" : "J";

    const sender = document.createElement("div");
    sender.className = "message-sender";
    sender.textContent = isUser ? "You" : "JurisAI";

    const time = document.createElement("div");
    time.className = "message-time";
    time.textContent = new Date().toLocaleTimeString();

    header.append(avatar, sender, time);

    const content = document.createElement("div");
    content.className = "message-content";
    if (markdown) {
      renderSafeMarkdown(content, text);
    } else {
      const p = document.createElement("p");
      p.textContent = text;
      content.appendChild(p);
    }

    messageDiv.append(header, content);
    if (!isUser && markdown && disclaimer.answer) {
      // A sibling of .message-content, so streaming re-renders of the answer
      // text never wipe it.
      const note = document.createElement("div");
      note.className = "answer-disclaimer";
      note.textContent = disclaimer.answer;
      messageDiv.appendChild(note);
    }
    chatContainer.appendChild(messageDiv);
    scrollChatToBottom();
    return content; // caller may keep appending to this (streaming)
  }

  function renderCrosswalkPanel(container, facts) {
    if (!facts || facts.length === 0) return;
    const details = document.createElement("details");
    details.className = "crosswalk-panel";
    const summary = document.createElement("summary");
    summary.textContent = `Verified IPC <-> BNS correspondence (${facts.length})`;
    details.appendChild(summary);
    for (const fact of facts) {
      const row = document.createElement("div");
      row.className = "crosswalk-row";

      const relation = document.createElement("div");
      relation.className = "crosswalk-relation";
      relation.textContent = fact.relation;

      const line = document.createElement("div");
      line.textContent = `BNS ${fact.bns_section} (${fact.bns_title}) <-> IPC ${fact.ipc_sections.join(", ")} (${fact.ipc_titles.join(", ")})`;

      row.append(relation, line);

      if (fact.notes) {
        const notes = document.createElement("div");
        notes.className = "crosswalk-notes";
        notes.textContent = fact.notes;
        row.appendChild(notes);
      }
      details.appendChild(row);
    }
    container.appendChild(details);
  }

  // ---------- SSE parsing over fetch (EventSource can't POST a body) ----------

  async function parseSSE(response, handlers) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        let eventName = "message";
        let data = "";
        for (const line of rawEvent.split("\n")) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        if (!data) continue;
        const handler = handlers[eventName];
        if (handler) handler(JSON.parse(data));
      }
    }
  }

  // ---------- Sending a message ----------

  async function handleUserMessage() {
    const message = userInput.value.trim();
    if (!message) return;

    addMessage({ isUser: true, text: message });
    userInput.value = "";
    sendButton.style.display = "none";
    abortButton.style.display = "flex";

    const selectedCorpus = corpusToggle.querySelector(".corpus-option.active").dataset.corpus;
    abortController = new AbortController();

    const botContent = addMessage({ isUser: false, text: "", markdown: true });
    botContent.classList.add("streaming-cursor");
    let buffer = "";

    try {
      const res = await apiFetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: abortController.signal,
        body: JSON.stringify({
          query: message,
          session_id: currentSessionId,
          corpus_mode: selectedCorpus || null,
          stream: true,
        }),
      });

      if (!res.ok || !res.body) {
        botContent.classList.remove("streaming-cursor");
        const p = document.createElement("p");
        p.className = "error";
        p.textContent = `Error: ${res.status}`;
        botContent.replaceChildren(p);
        return;
      }

      await parseSSE(res, {
        crosswalk: (facts) => renderCrosswalkPanel(botContent, facts),
        token: (chunk) => {
          buffer += chunk;
          renderSafeMarkdown(botContent, buffer);
          botContent.classList.add("streaming-cursor");
          scrollChatToBottom();
        },
        error: (payload) => {
          botContent.classList.remove("streaming-cursor");
          const p = document.createElement("p");
          p.className = "error";
          p.textContent = payload.detail || "The answer service is unavailable.";
          botContent.appendChild(p);
        },
        done: (payload) => {
          currentSessionId = payload.session_id;
          botContent.classList.remove("streaming-cursor");
          if (payload.persisted === false) {
            const note = document.createElement("p");
            note.className = "error";
            note.textContent = "This reply couldn't be saved to your history.";
            botContent.appendChild(note);
          }
          if (sessionListContainer.style.display === "block") loadHistory();
        },
      });
    } catch (err) {
      botContent.classList.remove("streaming-cursor");
      if (err.name !== "AbortError") {
        const p = document.createElement("p");
        p.className = "error";
        p.textContent = "An error occurred. Please try again.";
        botContent.appendChild(p);
      }
    } finally {
      sendButton.style.display = "flex";
      abortButton.style.display = "none";
      abortController = null;
    }
  }

  sendButton.addEventListener("click", handleUserMessage);
  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleUserMessage();
  });
  abortButton.addEventListener("click", () => {
    if (abortController) abortController.abort();
  });
  chatContainer.addEventListener("scroll", toggleScrollButton);
  scrollToBottomBtn.addEventListener("click", scrollChatToBottom);

  // ---------- Quick-prompt buttons (previously dead markup -- D054-adjacent) ----------

  actionsRow.querySelectorAll(".action-button").forEach((btn) => {
    btn.addEventListener("click", () => {
      userInput.value = btn.dataset.prompt || "";
      userInput.focus();
    });
  });

  // ---------- Corpus toggle ----------

  function setActiveCorpusButton(value) {
    corpusToggle.querySelectorAll(".corpus-option").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.corpus === value);
    });
  }

  corpusToggle.querySelectorAll(".corpus-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      setActiveCorpusButton(btn.dataset.corpus);
      try {
        localStorage.setItem(CORPUS_KEY, btn.dataset.corpus);
      } catch {
        // Per-viewer convenience only.
      }
    });
  });

  try {
    const saved = localStorage.getItem(CORPUS_KEY);
    if (saved !== null) setActiveCorpusButton(saved);
  } catch {
    // Default toggle state (Auto) already active in the markup.
  }

  // ---------- History ----------

  async function loadHistory() {
    sessionListContainer.style.display = "block";
    const res = await apiFetch("/api/history");
    if (!res.ok) {
      sessionList.replaceChildren();
      const p = document.createElement("p");
      p.className = "error";
      p.textContent = `Error: ${res.status}`;
      sessionList.appendChild(p);
      return;
    }
    const sessions = await res.json();
    sessionList.replaceChildren();
    if (sessions.length === 0) {
      const p = document.createElement("p");
      p.textContent = "No sessions yet.";
      sessionList.appendChild(p);
      return;
    }
    const template = document.getElementById("session-template");
    for (const session of sessions) {
      const node = document.importNode(template.content, true);
      const entry = node.querySelector(".session-entry");
      entry.dataset.sessionId = session.session_id;
      entry.querySelector(".session-title").textContent = session.title;
      entry.querySelector(".session-time").textContent = new Date(
        session.timestamp
      ).toLocaleDateString();

      entry.querySelector(".session-title").addEventListener("click", () => {
        loadSessionChats(session.session_id);
      });
      entry.querySelector(".edit-icon").addEventListener("click", () => {
        enableEditSessionTitle(session.session_id, session.title);
      });
      entry.querySelector(".delete-icon").addEventListener("click", () => {
        deleteSession(session.session_id, entry);
      });

      sessionList.appendChild(node);
    }
  }

  async function deleteSession(sessionId, entryEl) {
    if (!confirm("Are you sure you want to delete this session?")) return;
    const res = await apiFetch("/api/delete_session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
    if (res.ok) {
      entryEl.remove();
      if (currentSessionId === sessionId) currentSessionId = null;
    } else {
      alert("Failed to delete session. Please try again.");
    }
  }

  function enableEditSessionTitle(sessionId, currentTitle) {
    const entry = document.querySelector(`.session-entry[data-session-id="${CSS.escape(sessionId)}"]`);
    const titleSpan = entry.querySelector(".session-title");
    const actionsSpan = entry.querySelector(".session-actions");

    const input = document.createElement("input");
    input.type = "text";
    input.className = "session-title-input";
    input.value = currentTitle;
    input.maxLength = 50;
    titleSpan.replaceWith(input);

    actionsSpan.replaceChildren();
    const saveIcon = document.createElement("span");
    saveIcon.className = "save-icon small-icon";
    saveIcon.dataset.tooltip = "Save";
    saveIcon.textContent = "✓";
    actionsSpan.appendChild(saveIcon);

    input.focus();
    saveIcon.addEventListener("click", () => saveSessionTitle(sessionId, input.value));
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") saveSessionTitle(sessionId, input.value);
    });
  }

  async function saveSessionTitle(sessionId, newTitle) {
    const res = await apiFetch(`/api/rename_session/${encodeURIComponent(sessionId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: newTitle }),
    });
    if (res.ok) {
      loadHistory();
    } else {
      const data = await res.json().catch(() => ({}));
      alert("Error renaming session: " + (data.error || res.status));
    }
  }

  function loadSessionChats(sessionId) {
    document.querySelectorAll(".session-entry").forEach((e) => e.classList.remove("active"));
    const selected = document.querySelector(`.session-entry[data-session-id="${CSS.escape(sessionId)}"]`);
    if (selected) selected.classList.add("active");

    currentSessionId = sessionId;
    chatContainer.replaceChildren();

    apiFetch(`/api/session/${encodeURIComponent(sessionId)}`)
      .then((res) => res.json())
      .then((turns) => {
        for (const turn of turns) {
          addMessage({ isUser: true, text: turn.query });
          addMessage({ isUser: false, text: turn.response, markdown: true });
        }
      })
      .catch(() => {
        const p = document.createElement("p");
        p.className = "error";
        p.textContent = "Could not load this session.";
        chatContainer.appendChild(p);
      });
  }

  if (new URLSearchParams(window.location.search).get("view") === "history") {
    loadHistory();
  }

  // ---------- Speech input (Web Speech API -- reused from the legacy
  // prototype per CLAUDE.md; Chrome/Edge only, degrades to a hidden button
  // elsewhere, same as before). ----------

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onstart = () => {
      micButton.classList.add("listening");
      userInput.placeholder = "Listening...";
    };
    recognition.onresult = (event) => {
      userInput.value = event.results[0][0].transcript.trim();
      userInput.placeholder = "Type your message here...";
      micButton.classList.remove("listening");
      handleUserMessage();
    };
    recognition.onerror = (event) => {
      micButton.classList.remove("listening");
      userInput.placeholder = "Type your message here...";
      if (event.error !== "aborted") {
        alert("Speech recognition error: " + event.error);
      }
    };
    recognition.onend = () => {
      micButton.classList.remove("listening");
      userInput.placeholder = "Type your message here...";
    };
    micButton.addEventListener("click", () => recognition.start());
  } else {
    micButton.style.display = "none";
  }
});
