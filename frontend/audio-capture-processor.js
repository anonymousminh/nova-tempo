/**
 * AudioWorklet processor: captures mic audio as PCM Int16 chunks.
 *
 * The AudioContext should be created at the target sample rate (e.g. 16 kHz)
 * so the browser handles resampling from the mic's native rate.
 *
 * Sends ArrayBuffer (Int16 LE) messages to the main thread every ~32 ms
 * (CHUNK_FRAMES samples at the context sample rate).
 */
class AudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buffer = new Int16Array(512);
    this._offset = 0;
  }

  process(inputs) {
    const chan = inputs[0]?.[0];
    if (!chan) return true;

    for (let i = 0; i < chan.length; i++) {
      const s = Math.max(-1, Math.min(1, chan[i]));
      this._buffer[this._offset++] = s < 0 ? s * 0x8000 : s * 0x7fff;

      if (this._offset >= this._buffer.length) {
        this.port.postMessage(this._buffer.buffer.slice(0));
        this._offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("audio-capture-processor", AudioCaptureProcessor);
