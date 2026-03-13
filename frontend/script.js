/* ===================================================================
   Nova Tempo — voice-only frontend via Socket.IO + Nova Sonic
   =================================================================== */

const transcriptLog = document.getElementById("transcript-log");
const voiceBtn = document.getElementById("voice-btn");
const voiceStatus = document.getElementById("voice-status");

const isLocalDev =
  window.location.hostname === "localhost" ||
  window.location.hostname === "127.0.0.1";
const BACKEND_URL = isLocalDev ? "http://localhost:8000" : window.location.origin;

let novaUserId = localStorage.getItem("nova_user_id");
if (!novaUserId) {
  novaUserId =
    "nova_user_" +
    (crypto.randomUUID
      ? crypto.randomUUID()
      : "xxxx-xxxx-xxxx".replace(/x/g, () =>
          ((Math.random() * 16) | 0).toString(16)
        ));
  localStorage.setItem("nova_user_id", novaUserId);
}

const socket = io(BACKEND_URL, { auth: { user_id: novaUserId } });

socket.on("connect", () => console.log("Socket connected:", socket.id));
socket.on("disconnect", (reason) => {
  console.log("Socket disconnected:", reason);
  if (voiceActive) stopVoice();
});
socket.on("connect_error", (err) => console.error("Socket error:", err.message));

// ---- helpers --------------------------------------------------------

function addMessage(text, cls) {
  const el = document.createElement("div");
  el.className = "msg " + cls;
  el.textContent = text;
  transcriptLog.appendChild(el);
  transcriptLog.scrollTop = transcriptLog.scrollHeight;
  return el;
}

// =====================================================================
//  Voice mode
// =====================================================================

let voiceActive = false;
let captureCtx = null;
let micStream = null;
let workletNode = null;
let sourceNode = null;

let playbackCtx = null;
let playbackTime = 0;

let userTranscriptEl = null;
let agentTranscriptEl = null;

// ---- voice button ---------------------------------------------------

voiceBtn.addEventListener("click", () => {
  if (voiceActive) {
    stopVoice();
  } else {
    startVoice();
  }
});

async function startVoice() {
  if (voiceActive) return;

  voiceBtn.classList.add("connecting");
  voiceStatus.textContent = "Connecting…";

  try {
    socket.emit("voice_start");
  } catch (err) {
    voiceBtn.classList.remove("connecting");
    voiceStatus.textContent = "Error: " + err.message;
  }
}

function stopVoice() {
  socket.emit("voice_stop");
  teardownAudio();
  voiceActive = false;
  voiceBtn.classList.remove("active", "connecting");
  voiceStatus.textContent = "Click the mic to start";
}

// ---- Socket.IO voice events -----------------------------------------

socket.on("voice_started", async (config) => {
  console.log("Voice started, config:", config);
  try {
    await setupAudio(config);
    voiceActive = true;
    voiceBtn.classList.remove("connecting");
    voiceBtn.classList.add("active");
    voiceStatus.textContent = "Listening — click mic to stop";
  } catch (err) {
    console.error("Audio setup failed:", err);
    voiceStatus.textContent = "Mic error: " + err.message;
    voiceBtn.classList.remove("connecting");
    socket.emit("voice_stop");
  }
});

socket.on("voice_stopped", () => {
  teardownAudio();
  voiceActive = false;
  voiceBtn.classList.remove("active", "connecting");
  voiceStatus.textContent = "Click the mic to start";
});

socket.on("voice_audio_out", (data) => {
  if (!voiceActive) return;
  playAudioChunk(data.audio, data.sampleRate);
});

socket.on("voice_transcript", (data) => {
  if (data.role === "user") {
    if (!userTranscriptEl) {
      userTranscriptEl = addMessage("", "user");
    }
    userTranscriptEl.textContent = data.currentTranscript || data.text;
    if (data.isFinal) {
      userTranscriptEl = null;
    }
  } else {
    if (!agentTranscriptEl) {
      agentTranscriptEl = addMessage("", "agent streaming");
    }
    if (data.currentTranscript) {
      agentTranscriptEl.textContent = data.currentTranscript;
    } else {
      agentTranscriptEl.textContent += data.text;
    }
    transcriptLog.scrollTop = transcriptLog.scrollHeight;
    if (data.isFinal) {
      agentTranscriptEl.classList.remove("streaming");
      agentTranscriptEl = null;
    }
  }
});

socket.on("voice_interrupted", () => {
  if (agentTranscriptEl) {
    agentTranscriptEl.classList.remove("streaming");
    agentTranscriptEl = null;
  }
  clearPlaybackQueue();
});

socket.on("voice_error", (data) => {
  addMessage("Voice error: " + data.error, "error");
  stopVoice();
});

// ---- audio capture --------------------------------------------------

async function setupAudio(config) {
  const inputRate = config.inputSampleRate || 16000;
  const outputRate = config.outputSampleRate || 16000;

  captureCtx = new AudioContext({ sampleRate: inputRate });
  await captureCtx.audioWorklet.addModule("./audio-capture-processor.js");

  micStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  sourceNode = captureCtx.createMediaStreamSource(micStream);
  workletNode = new AudioWorkletNode(captureCtx, "audio-capture-processor");

  workletNode.port.onmessage = (e) => {
    const pcmBuffer = e.data;
    const b64 = arrayBufferToBase64(pcmBuffer);
    socket.emit("voice_audio_in", { audio: b64 });
  };

  sourceNode.connect(workletNode);
  workletNode.connect(captureCtx.destination);

  playbackCtx = new AudioContext({ sampleRate: outputRate });
  playbackTime = 0;
}

function teardownAudio() {
  if (workletNode) { workletNode.disconnect(); workletNode = null; }
  if (sourceNode) { sourceNode.disconnect(); sourceNode = null; }
  if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
  if (captureCtx) { captureCtx.close().catch(() => {}); captureCtx = null; }
  if (playbackCtx) { playbackCtx.close().catch(() => {}); playbackCtx = null; }
  userTranscriptEl = null;
  agentTranscriptEl = null;
}

// ---- audio playback -------------------------------------------------

function playAudioChunk(base64Audio, sampleRate) {
  if (!playbackCtx) return;

  const bytes = atob(base64Audio);
  const buf = new ArrayBuffer(bytes.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < bytes.length; i++) view[i] = bytes.charCodeAt(i);

  const int16 = new Int16Array(buf);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768;

  const audioBuf = playbackCtx.createBuffer(1, float32.length, sampleRate);
  audioBuf.getChannelData(0).set(float32);

  const src = playbackCtx.createBufferSource();
  src.buffer = audioBuf;
  src.connect(playbackCtx.destination);

  const now = playbackCtx.currentTime;
  if (playbackTime < now) playbackTime = now;
  src.start(playbackTime);
  playbackTime += audioBuf.duration;
}

function clearPlaybackQueue() {
  if (playbackCtx) {
    playbackTime = playbackCtx.currentTime;
  }
}

// ---- util -----------------------------------------------------------

function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}
