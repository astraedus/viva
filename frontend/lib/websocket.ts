/**
 * WebSocket client for bidirectional audio streaming with the Viva backend.
 *
 * Audio format sent to server: PCM 16-bit, 16kHz, mono (from AudioWorklet).
 * Audio format received from server: PCM 16-bit, 24kHz, mono (Gemini native output).
 */

export type WSMessageType =
  | 'audio_chunk'
  | 'transcript'
  | 'ai_response'
  | 'question'
  | 'session_end'
  | 'error'
  | 'barge_in'
  | 'status';

export interface WSMessage {
  type: WSMessageType;
  payload: Record<string, unknown>;
}

export interface AudioStreamCallbacks {
  onMessage: (msg: WSMessage) => void;
  onAudioChunk: (chunk: ArrayBuffer) => void;
  onConnected: () => void;
  onDisconnected: () => void;
  onError: (err: string) => void;
}

export class VivaWebSocket {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private callbacks: AudioStreamCallbacks;
  private reconnectAttempts = 0;
  private maxReconnects = 3;
  private baseUrl: string;

  constructor(sessionId: string, callbacks: AudioStreamCallbacks, baseUrl?: string) {
    this.sessionId = sessionId;
    this.callbacks = callbacks;
    this.baseUrl = baseUrl ?? (process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000');
  }

  connect(): void {
    const url = `${this.baseUrl}/ws/${this.sessionId}`;

    this.ws = new WebSocket(url);
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.callbacks.onConnected();
    };

    this.ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary frame — raw PCM audio from Gemini
        this.callbacks.onAudioChunk(event.data);
      } else {
        // JSON message
        try {
          const msg = JSON.parse(event.data as string) as WSMessage;
          this.callbacks.onMessage(msg);
        } catch {
          console.error('[VivaWS] Failed to parse JSON message', event.data);
        }
      }
    };

    this.ws.onerror = (event) => {
      console.error('[VivaWS] WebSocket error', event);
      this.callbacks.onError('WebSocket connection error');
    };

    this.ws.onclose = (event) => {
      this.callbacks.onDisconnected();
      if (!event.wasClean && this.reconnectAttempts < this.maxReconnects) {
        const delay = Math.pow(2, this.reconnectAttempts) * 500;
        this.reconnectAttempts++;
        console.log(`[VivaWS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
        setTimeout(() => this.connect(), delay);
      }
    };
  }

  sendAudio(pcmChunk: ArrayBuffer): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(pcmChunk);
    }
  }

  sendBargeIn(): void {
    this.sendJSON({ type: 'barge_in', payload: {} });
  }

  sendStatus(message: string): void {
    this.sendJSON({ type: 'status', payload: { message } });
  }

  private sendJSON(msg: WSMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  disconnect(): void {
    this.maxReconnects = 0; // Prevent auto-reconnect
    this.ws?.close(1000, 'Client disconnecting');
    this.ws = null;
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// ---------------------------------------------------------------------------
// AudioWorklet processor source (inlined as a Blob URL)
// Converts Float32 microphone data to Int16 PCM for transmission.
// ---------------------------------------------------------------------------

export const AUDIO_PROCESSOR_SRC = `
class PcmProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;

    const float32 = input[0];
    const int16 = new Int16Array(float32.length);

    for (let i = 0; i < float32.length; i++) {
      const clamped = Math.max(-1, Math.min(1, float32[i]));
      int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
    }

    this.port.postMessage(int16.buffer, [int16.buffer]);
    return true;
  }
}

registerProcessor('pcm-processor', PcmProcessor);
`;

export function createAudioProcessorUrl(): string {
  const blob = new Blob([AUDIO_PROCESSOR_SRC], { type: 'application/javascript' });
  return URL.createObjectURL(blob);
}

// ---------------------------------------------------------------------------
// PCM audio playback for Gemini responses (24kHz mono)
// ---------------------------------------------------------------------------

export class PcmPlayer {
  private audioCtx: AudioContext | null = null;
  private nextStartTime = 0;
  private sampleRate: number;

  constructor(sampleRate = 24000) {
    this.sampleRate = sampleRate;
  }

  private ensureContext(): AudioContext {
    if (!this.audioCtx || this.audioCtx.state === 'closed') {
      this.audioCtx = new AudioContext({ sampleRate: this.sampleRate });
      this.nextStartTime = this.audioCtx.currentTime;
    }
    return this.audioCtx;
  }

  playChunk(pcmBuffer: ArrayBuffer): void {
    const ctx = this.ensureContext();
    const int16 = new Int16Array(pcmBuffer);
    const float32 = new Float32Array(int16.length);

    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / (int16[i] < 0 ? 0x8000 : 0x7fff);
    }

    const audioBuffer = ctx.createBuffer(1, float32.length, this.sampleRate);
    audioBuffer.copyToChannel(float32, 0);

    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    const startAt = Math.max(ctx.currentTime, this.nextStartTime);
    source.start(startAt);
    this.nextStartTime = startAt + audioBuffer.duration;
  }

  stop(): void {
    this.audioCtx?.close();
    this.audioCtx = null;
  }
}
