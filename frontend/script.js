// DOM Elements
const enableButton = document.getElementById("enable-button");
const output = document.getElementById("output");
const startButton = document.getElementById("start-button");
const stopButton = document.getElementById("stop-button");
const playbackContainer = document.getElementById("playback-container");
const playbackAudio = document.getElementById("playback");

// State
let streamMedia = null;
let recorderMedia = null;
const audioChunks = [];

// WebSocket: connect to backend via Socket.IO
// (Live Server uses 127.0.0.1:5500; backend runs on port 3000)
const isLocalDev =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
const BACKEND_URL = isLocalDev ? "http://localhost:3000" : window.location.origin;
const socket = io(BACKEND_URL);

socket.on("connect", () => {
    console.log("Socket connected:", socket.id);
});
socket.on("disconnect", (reason) => {
    console.log("Socket disconnected:", reason);
});
socket.on("connect_error", (err) => {
    console.error("Socket connection error:", err.message);
});

function enableMicrophone() {
    enableButton.addEventListener("click", () => {
        navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
            streamMedia = stream;
            recorderMedia = new MediaRecorder(streamMedia);

            recorderMedia.addEventListener("dataavailable", (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                    // Stream chunk to backend for Strands Agent
                    if (socket.connected) socket.emit("audio-chunk", event.data);
                }
            });

            recorderMedia.addEventListener("stop", () => {
                if (audioChunks.length === 0) return;
                const mimeType = recorderMedia.mimeType || "audio/webm";
                const audioBlob = new Blob(audioChunks, { type: mimeType });
                const audioUrl = URL.createObjectURL(audioBlob);
                playbackAudio.src = audioUrl;
                playbackContainer.hidden = false;
                output.textContent = "Recording finished. Play below.";
                audioChunks.length = 0;
            });

            output.hidden = false;
            output.textContent = "Microphone enabled";
        }).catch((error) => {
            console.error("Error enabling microphone:", error);
            output.hidden = false;
            output.textContent = "Error enabling microphone: " + error;
        });
    });
}

function setupRecordingButtons() {
    startButton.addEventListener("click", () => {
        if (!streamMedia || !recorderMedia) {
            output.textContent = "Enable the microphone first.";
            output.hidden = false;
            return;
        }
        audioChunks.length = 0;
        recorderMedia.start(250); // emit dataavailable every 250 ms
        output.textContent = "Recording…";
    });

    stopButton.addEventListener("click", () => {
        if (!recorderMedia || recorderMedia.state === "inactive") return;
        recorderMedia.stop();
    });
}

enableMicrophone();
setupRecordingButtons();