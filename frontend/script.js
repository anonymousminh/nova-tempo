const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");

const isLocalDev =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
const BACKEND_URL = isLocalDev ? "http://localhost:8000" : window.location.origin;
const socket = io(BACKEND_URL);

socket.on("connect", () => console.log("Socket connected:", socket.id));
socket.on("disconnect", (reason) => console.log("Socket disconnected:", reason));
socket.on("connect_error", (err) => console.error("Socket error:", err.message));

function addMessage(text, cls) {
    const el = document.createElement("div");
    el.className = "msg " + cls;
    el.textContent = text;
    chatLog.appendChild(el);
    chatLog.scrollTop = chatLog.scrollHeight;
    return el;
}

let streamEl = null;
let streamText = "";

socket.on("agent_stream", (data) => {
    if (!streamEl) {
        streamEl = addMessage("", "agent streaming");
    }
    streamText += data.data || "";
    streamEl.textContent = streamText;
    chatLog.scrollTop = chatLog.scrollHeight;
});

socket.on("agent_result", (data) => {
    if (streamEl) {
        streamEl.classList.remove("streaming");
        if (data.text) streamEl.textContent = data.text;
    }
    streamEl = null;
    streamText = "";
    chatInput.disabled = false;
    chatForm.querySelector("button").disabled = false;
});

socket.on("agent_error", (data) => {
    if (streamEl) {
        streamEl.classList.remove("streaming");
        streamEl.classList.add("error");
        streamEl.textContent = data.error;
    } else {
        addMessage(data.error, "error");
    }
    streamEl = null;
    streamText = "";
    chatInput.disabled = false;
    chatForm.querySelector("button").disabled = false;
});

chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    addMessage(text, "user");
    chatInput.value = "";
    chatInput.disabled = true;
    chatForm.querySelector("button").disabled = true;
    socket.emit("agent_message", { message: text });
});
