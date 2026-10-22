/**
 * chat.js
 * Handles:
 *  - Sending questions to /ask
 *  - Streaming SSE tokens into the UI
 *  - Rendering markdown via marked.js
 *  - Fetching and showing sources
 *  - Quick chips, sidebar toggle, auto-resize textarea
 */
 
// ── State ────────────────────────────────────
let isStreaming  = false;
let currentSources = [];   // sources for most recent answer
 
// ── Marked config ────────────────────────────
marked.setOptions({
  breaks: true,
  gfm:    true,
  // Never execute scripts from markdown
  sanitize: false,
});
 
 
// ── DOM helpers ──────────────────────────────
const $ = id => document.getElementById(id);
 
function scrollToBottom() {
  var c = $("messagesContainer");
  c.scrollTop = c.scrollHeight;
}
 
function getTime() {
  var d = new Date();
  var h = d.getHours().toString().padStart(2, "0");
  var m = d.getMinutes().toString().padStart(2, "0");
  return h + ":" + m;
}
 
 
// ── Welcome screen ───────────────────────────
function hideWelcome() {
  var ws = $("welcomeScreen");
  if (ws) ws.remove();
}
 
 
// ── Message rendering ────────────────────────
 
function appendUserMessage(text) {
  hideWelcome();
  var c = $("messagesContainer");
 
  var el = document.createElement("div");
  el.className = "message user";
  el.innerHTML = [
    '<div class="msg-avatar">U</div>',
    '<div class="msg-body">',
      '<div class="msg-bubble">' + escapeHtml(text) + '</div>',
      '<div class="msg-meta"><span class="msg-time">' + getTime() + '</span></div>',
    '</div>'
  ].join("");
 
  c.appendChild(el);
  scrollToBottom();
}
 
 
function appendTypingIndicator() {
  var c = $("messagesContainer");
 
  var el = document.createElement("div");
  el.className = "message bot";
  el.id = "typingMsg";
  el.innerHTML = [
    '<div class="msg-avatar">AI</div>',
    '<div class="msg-body">',
      '<div class="msg-bubble">',
        '<div class="typing-indicator">',
          '<span></span><span></span><span></span>',
        '</div>',
      '</div>',
    '</div>'
  ].join("");
 
  c.appendChild(el);
  scrollToBottom();
  return el;
}
 
 
function replaceBotMessage(rawText, sources) {
  // Remove typing indicator
  var typing = $("typingMsg");
  if (typing) typing.remove();
 
  var c = $("messagesContainer");
 
  var el = document.createElement("div");
  el.className = "message bot";
 
  // Render markdown
  var rendered = marked.parse(rawText);
 
  // Build sources button if we have any
  var sourcesHtml = "";
  if (sources && sources.length > 0) {
    sourcesHtml = '<button class="sources-btn" onclick="openDrawer()">📎 ' + sources.length + ' sources</button>';
  }
 
  el.innerHTML = [
    '<div class="msg-avatar">AI</div>',
    '<div class="msg-body">',
      '<div class="msg-bubble" id="lastBotBubble">' + rendered + '</div>',
      '<div class="msg-meta">',
        '<span class="msg-time">' + getTime() + '</span>',
        sourcesHtml,
      '</div>',
    '</div>'
  ].join("");
 
  c.appendChild(el);
  scrollToBottom();
}
 
 
// ── Streaming bot message ────────────────────
 
function createStreamingBubble() {
  // Remove typing indicator
  var typing = $("typingMsg");
  if (typing) typing.remove();
 
  var c = $("messagesContainer");
 
  var el = document.createElement("div");
  el.className = "message bot";
  el.id = "streamingMsg";
  el.innerHTML = [
    '<div class="msg-avatar">AI</div>',
    '<div class="msg-body">',
      '<div class="msg-bubble streaming-cursor" id="streamBubble"></div>',
    '</div>'
  ].join("");
 
  c.appendChild(el);
  scrollToBottom();
}
 
function updateStreamingBubble(rawText) {
  var bubble = $("streamBubble");
  if (!bubble) return;
  bubble.innerHTML = marked.parse(rawText);
  scrollToBottom();
}
 
function finaliseStreamingBubble(rawText, sources) {
  var el = $("streamingMsg");
  if (!el) return;
 
  var bubble = $("streamBubble");
  if (bubble) {
    bubble.classList.remove("streaming-cursor");
    bubble.innerHTML = marked.parse(rawText);
  }
 
  // Add meta row
  var sourcesHtml = "";
  if (sources && sources.length > 0) {
    sourcesHtml = '<button class="sources-btn" onclick="openDrawer()">📎 ' + sources.length + ' sources</button>';
  }
 
  var meta = document.createElement("div");
  meta.className = "msg-meta";
  meta.innerHTML = '<span class="msg-time">' + getTime() + '</span>' + sourcesHtml;
  el.querySelector(".msg-body").appendChild(meta);
 
  scrollToBottom();
}
 
 
// ── Main submit flow ─────────────────────────
 
async function submitQuestion() {
  if (isStreaming) return;
 
  var input = $("questionInput");
  var question = input.value.trim();
  if (!question) return;
 
  input.value = "";
  autoResize(input);
 
  isStreaming = true;
  $("sendBtn").disabled = true;
 
  appendUserMessage(question);
  appendTypingIndicator();
 
  // Fetch sources in parallel (non-blocking)
  currentSources = [];
  fetchSources(question).then(function(sources) {
    currentSources = sources;
  });
 
  // Small delay so typing indicator shows briefly
  await sleep(300);
  createStreamingBubble();
 
  var fullText = "";
 
  try {
    var resp = await fetch("/ask", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ question: question })
    });
 
    if (!resp.ok) {
      throw new Error("Server error " + resp.status);
    }
 
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
 
    while (true) {
      var result = await reader.read();
      if (result.done) break;
 
      var chunk = decoder.decode(result.value, { stream: true });
      var lines  = chunk.split("\n");
 
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (!line.startsWith("data:")) continue;
 
        var data = line.slice(5).trim();
        if (data === "[DONE]") break;
 
        try {
          var parsed = JSON.parse(data);
          if (parsed.token) {
            fullText += parsed.token;
            updateStreamingBubble(fullText);
          }
        } catch (e) {
          // skip malformed SSE line
        }
      }
    }
 
  } catch (err) {
    fullText = "⚠️ **Error:** " + err.message + ". Please try again.";
  }
 
  finaliseStreamingBubble(fullText, currentSources);
 
  isStreaming = false;
  $("sendBtn").disabled = false;
  input.focus();
}
 
 
// ── Sources ───────────────────────────────────
 
async function fetchSources(question) {
  try {
    var resp = await fetch("/sources", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ question: question })
    });
    if (!resp.ok) return [];
    var data = await resp.json();
    return data.sources || [];
  } catch (e) {
    return [];
  }
}
 
function openDrawer() {
  var drawer  = $("sourcesDrawer");
  var overlay = $("drawerOverlay");
  var body    = $("drawerBody");
 
  body.innerHTML = "";
 
  if (!currentSources || currentSources.length === 0) {
    body.innerHTML = '<p style="color:var(--text-3);font-size:13px;text-align:center;padding:24px">No sources available.</p>';
  } else {
    currentSources.forEach(function(s) {
      var card = document.createElement("div");
      card.className = "source-card";
      card.innerHTML = [
        '<div class="source-card-title">' + escapeHtml(s.title || s.source || "Source") + '</div>',
        '<div class="source-card-text">'  + escapeHtml(s.text.slice(0, 400)) + (s.text.length > 400 ? "…" : "") + '</div>',
        '<div class="source-card-score">Relevance: ' + (1 - s.score).toFixed(2) + '</div>',
      ].join("");
      body.appendChild(card);
    });
  }
 
  drawer.classList.add("open");
  overlay.classList.add("active");
}
 
function closeDrawer() {
  $("sourcesDrawer").classList.remove("open");
  $("drawerOverlay").classList.remove("active");
}
 
 
// ── Utility ───────────────────────────────────
 
function sendQuick(text) {
  $("questionInput").value = text;
  submitQuestion();
}
 
function clearChat() {
  var c = $("messagesContainer");
  c.innerHTML = "";
 
  // Re-add welcome screen
  var ws = document.createElement("div");
  ws.className = "welcome-screen";
  ws.id = "welcomeScreen";
  ws.innerHTML = [
    '<div class="welcome-icon">',
      '<svg viewBox="0 0 80 80" fill="none" xmlns="http://www.w3.org/2000/svg">',
        '<circle cx="40" cy="40" r="38" stroke="url(#g1)" stroke-width="2" fill="none" opacity="0.4"/>',
        '<circle cx="40" cy="40" r="28" stroke="url(#g1)" stroke-width="1.5" fill="none" opacity="0.25"/>',
        '<path d="M26 40 C26 32 33 26 40 26 C47 26 54 32 54 40 C54 48 47 54 40 54 C36 54 32 52 30 48" stroke="url(#g1)" stroke-width="2.5" stroke-linecap="round" fill="none"/>',
        '<circle cx="40" cy="40" r="5" fill="url(#g1)"/>',
        '<defs><linearGradient id="g1" x1="10" y1="10" x2="70" y2="70">',
        '<stop offset="0%" stop-color="#0066CC"/><stop offset="100%" stop-color="#003d7a"/>',
        '</linearGradient></defs></svg></div>',
    '<h1 class="welcome-title">Hello, I\'m SRM Assistant</h1>',
    '<p class="welcome-subtitle">Ask me anything about SRM Institute — admissions, courses, fees, placements, campus life, and more.</p>',
    '<div class="welcome-chips">',
      '<button class="welcome-chip" onclick="sendQuick(\'What is the SRMJEEE cutoff for CSE?\')">SRMJEEE cutoffs for CSE?</button>',
      '<button class="welcome-chip" onclick="sendQuick(\'What are the top companies that recruit from SRM?\')">Top recruiting companies?</button>',
      '<button class="welcome-chip" onclick="sendQuick(\'What facilities are available on the SRM campus?\')">Campus facilities?</button>',
    '</div>',
  ].join("");
  c.appendChild(ws);
 
  currentSources = [];
  isStreaming = false;
  $("sendBtn").disabled = false;
}
 
function handleKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    submitQuestion();
  }
}
 
function autoResize(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 180) + "px";
}
 
function toggleSidebar() {
  document.querySelector(".sidebar").classList.toggle("open");
}
 
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
 
function sleep(ms) {
  return new Promise(function(r) { setTimeout(r, ms); });
}
 
