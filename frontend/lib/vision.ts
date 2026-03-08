/**
 * Camera frame capture and REST API client for body language analysis.
 *
 * Captures a JPEG frame from the video element every 2 seconds,
 * sends it to POST /api/analyze-frame, and returns the analysis.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export interface BodyLanguageResult {
  eye_contact: boolean;
  posture: string;
  expression: string;
  tips: string[];
  confidence_score: number;
}

/**
 * Capture a JPEG frame from a <video> element and return it as a base64 string.
 */
export function captureFrame(
  videoEl: HTMLVideoElement,
  quality = 0.7,
): string | null {
  if (videoEl.readyState < videoEl.HAVE_CURRENT_DATA) return null;
  if (videoEl.videoWidth === 0 || videoEl.videoHeight === 0) return null;

  const canvas = document.createElement('canvas');
  // Downscale to 640x480 max to keep payload small
  const maxW = 640;
  const maxH = 480;
  const scale = Math.min(maxW / videoEl.videoWidth, maxH / videoEl.videoHeight, 1);
  canvas.width = Math.round(videoEl.videoWidth * scale);
  canvas.height = Math.round(videoEl.videoHeight * scale);

  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

  // Strip the "data:image/jpeg;base64," prefix — we only want raw base64
  const dataUrl = canvas.toDataURL('image/jpeg', quality);
  return dataUrl.split(',')[1] ?? null;
}

/**
 * Send a base64 frame to the backend for analysis.
 */
export async function analyzeFrame(
  sessionId: string,
  frameB64: string,
): Promise<BodyLanguageResult> {
  const response = await fetch(`${API_BASE}/api/analyze-frame`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, frame_data: frameB64 }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`analyzeFrame failed (${response.status}): ${text}`);
  }

  return response.json() as Promise<BodyLanguageResult>;
}

/**
 * Start periodic frame capture and analysis.
 *
 * @returns cleanup function — call to stop
 */
export function startFrameCapture(
  videoEl: HTMLVideoElement,
  sessionId: string,
  onResult: (result: BodyLanguageResult) => void,
  onError?: (err: Error) => void,
  intervalMs = 2000,
): () => void {
  let active = true;

  const tick = async () => {
    if (!active) return;

    try {
      const frame = captureFrame(videoEl);
      if (frame) {
        const result = await analyzeFrame(sessionId, frame);
        if (active) onResult(result);
      }
    } catch (err) {
      if (active) onError?.(err instanceof Error ? err : new Error(String(err)));
    }

    if (active) setTimeout(tick, intervalMs);
  };

  setTimeout(tick, intervalMs); // First capture after initial interval
  return () => { active = false; };
}

/**
 * Create and start a webcam stream on a <video> element.
 *
 * @returns cleanup function that stops all tracks
 */
export async function startCamera(videoEl: HTMLVideoElement): Promise<() => void> {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: {
      width: { ideal: 1280 },
      height: { ideal: 720 },
      facingMode: 'user',
    },
    audio: false, // Audio handled separately via AudioWorklet
  });

  videoEl.srcObject = stream;
  await videoEl.play();

  return () => {
    stream.getTracks().forEach((t) => t.stop());
    videoEl.srcObject = null;
  };
}

/**
 * Start microphone stream and return the MediaStream.
 * Caller is responsible for creating the AudioWorklet pipeline.
 */
export async function startMicrophone(): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: {
      sampleRate: 16000,
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    video: false,
  });
}
