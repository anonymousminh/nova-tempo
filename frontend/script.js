// DOM Elements
const enableButton = document.getElementById("enable-button");
const output = document.getElementById("output");
const startButton = document.getElementById("start-button");
const stopButton = document.getElementById("stop-button");
const playbackContainer = document.getElementById("playback-container");
const playbackAudio = document.getElementById("playback");
const canvasOut = document.getElementById("waveform-out");
const canvasIn = document.getElementById("waveform-in");

// State
let streamMedia = null;
let recorderMedia = null;
const audioChunks = [];

// Web Audio: one context for playback and analysers
let audioContext = null;
let analyserOut = null;   // microphone / outgoing
let analyserIn = null;    // echoed / incoming
let sourceOutStream = null;
const incomingChunkQueue = [];
const CHUNKS_TO_DECODE = 4;  // ~1 second (4 × 250ms) before decode & play
let nextPlayTime = 0;

// Backend: FastAPI + Socket.IO on port 8000
const isLocalDev =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";
const BACKEND_URL = isLocalDev ? "http://localhost:8000" : window.location.origin;
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

// ---------------------------------------------------------------------------
// Receive binary audio from server (Echo BidiAgent) and play via Web Audio API
// ---------------------------------------------------------------------------
socket.on("audio_response", (data) => {
    if (!data) return;
    let buf = data;
    if (data instanceof ArrayBuffer) {
        buf = data;
    } else if (data instanceof Blob) {
        data.arrayBuffer().then(ab => enqueueIncoming(ab));
        return;
    } else if (typeof data === "object" && data.byteLength != null) {
        buf = data.buffer || data;
    }
    enqueueIncoming(buf);
});

function enqueueIncoming(arrayBuffer) {
    if (!arrayBuffer || arrayBuffer.byteLength === 0) return;
    incomingChunkQueue.push(arrayBuffer);
    drainIncomingQueue();
}

function drainIncomingQueue() {
    if (!audioContext || incomingChunkQueue.length < CHUNKS_TO_DECODE) return;
    const chunks = incomingChunkQueue.splice(0, CHUNKS_TO_DECODE);
    const totalLength = chunks.reduce((acc, c) => acc + c.byteLength, 0);
    const merged = new Uint8Array(totalLength);
    let offset = 0;
    for (const c of chunks) {
        merged.set(new Uint8Array(c), offset);
        offset += c.byteLength;
    }
    const blob = new Blob([merged], { type: "audio/webm" });
    blob.arrayBuffer().then((ab) => {
        audioContext.decodeAudioData(ab).then((buffer) => {
            playDecodedBuffer(buffer);
        }).catch((err) => {
            console.warn("Decode failed, re-queuing chunks", err);
            chunks.forEach(c => incomingChunkQueue.unshift(c));
        });
    });
}

function playDecodedBuffer(buffer) {
    const now = audioContext.currentTime;
    const start = Math.max(now, nextPlayTime);
    nextPlayTime = start + buffer.duration;
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(analyserIn);
    source.start(start);
    source.stop(start + buffer.duration);
}

// ---------------------------------------------------------------------------
// Waveform: Canvas + AnalyserNode for outgoing and incoming
// ---------------------------------------------------------------------------
function drawWaveform(canvas, analyser, color) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    if (!analyser) {
        ctx.fillStyle = "rgba(20,20,30,0.3)";
        ctx.fillRect(0, 0, w, h);
        return;
    }
    const dataArray = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(dataArray);

    ctx.fillStyle = "rgba(20,20,30,0.3)";
    ctx.fillRect(0, 0, w, h);
    ctx.lineWidth = 2;
    ctx.strokeStyle = color;
    ctx.beginPath();
    const sliceWidth = w / dataArray.length;
    let x = 0;
    for (let i = 0; i < dataArray.length; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * h) / 2 + h / 2;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        x += sliceWidth;
    }
    ctx.lineTo(w, h / 2);
    ctx.stroke();
}

function tickWaveform() {
    drawWaveform(canvasOut, analyserOut, "#3b82f6");
    drawWaveform(canvasIn, analyserIn, "#22c55e");
    requestAnimationFrame(tickWaveform);
}

// ---------------------------------------------------------------------------
// Microphone: MediaRecorder 250ms chunks + Web Audio for waveform
// ---------------------------------------------------------------------------
function ensureAudioContext() {
    if (audioContext) return audioContext;
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const fftSize = 2048;
    analyserOut = audioContext.createAnalyser();
    analyserOut.fftSize = fftSize;
    analyserIn = audioContext.createAnalyser();
    analyserIn.fftSize = fftSize;
    analyserIn.connect(audioContext.destination);
    tickWaveform();
    return audioContext;
}

function enableMicrophone() {
  enableButton.addEventListener("click", () => {
    navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
      streamMedia = stream;
      ensureAudioContext();
      sourceOutStream = audioContext.createMediaStreamSource(stream);
      sourceOutStream.connect(analyserOut);
      // Outgoing analyser for waveform only (no speaker output)

      const mimeOpt = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? { mimeType: "audio/webm;codecs=opus" }
          : {};
      recorderMedia = new MediaRecorder(streamMedia, mimeOpt);

      recorderMedia.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) {
          audioChunks.push(event.data);
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
    nextPlayTime = 0;
    recorderMedia.start(250);
    output.textContent = "Recording… (250ms chunks → server echo)";
  });

  stopButton.addEventListener("click", () => {
    if (!recorderMedia || recorderMedia.state === "inactive") return;
    recorderMedia.stop();
  });
}

enableMicrophone();
setupRecordingButtons();

// Start waveform animation loop (draws when analysers exist after mic enable)
tickWaveform();
