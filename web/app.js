const apiUrl = window.CHAT_API_URL;
const messagesEl = document.getElementById("messages");
const form = document.getElementById("chat-form");
const input = document.getElementById("message");
const newChatButton = document.getElementById("new-chat");

function getSessionId() {
  try {
    let id = localStorage.getItem("sessionId");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("sessionId", id);
    }
    return id;
  } catch (e) {
    // Browser storage is blocked: keep the id for this page only.
    window.fallbackSessionId = window.fallbackSessionId || crypto.randomUUID();
    return window.fallbackSessionId;
  }
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = "msg " + role;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function loadHistory() {
  try {
    const res = await fetch(`${apiUrl}/history/${getSessionId()}`);
    if (!res.ok) return;
    const data = await res.json();
    data.messages.forEach((m) => addMessage(m.role, m.content));
  } catch (e) {
    addMessage("error", "Could not reach the chat API.");
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  addMessage("user", text);
  input.value = "";
  form.querySelector("button").disabled = true;
  try {
    const res = await fetch(`${apiUrl}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sessionId: getSessionId(), message: text }),
    });
    const data = await res.json();
    if (res.ok) {
      addMessage("assistant", data.reply);
    } else {
      addMessage("error", data.error || "Something went wrong.");
    }
  } catch (e) {
    addMessage("error", "Could not reach the chat API.");
  } finally {
    form.querySelector("button").disabled = false;
    input.focus();
  }
});

newChatButton.addEventListener("click", () => {
  try {
    localStorage.removeItem("sessionId");
  } catch (e) {
    window.fallbackSessionId = null;
  }
  messagesEl.innerHTML = "";
});

loadHistory();
