const http = require("http");
const { Server } = require("socket.io");

const server = http.createServer();
const io = new Server(server, {
    cors: { origin: "*", methods: ["GET", "POST"] },
});

io.on("connection", (socket) => {
    console.log("Client connected:", socket.id);

    // Incoming audio data chunks (streamed from client MediaRecorder every ~250ms)
    socket.on("audio-chunk", (chunk) => {
        const size = Buffer.isBuffer(chunk) ? chunk.length : (chunk?.byteLength ?? 0);
        if (size > 0) {
            // TODO: forward to Strands Agent (e.g. pipe into speech pipeline)
            console.log("Audio chunk received:", size, "bytes");
        }
    });

    socket.on("disconnect", (reason) => {
        console.log("Client disconnected:", socket.id, reason);
    });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
    console.log("Backend listening on http://localhost:" + PORT);
});
