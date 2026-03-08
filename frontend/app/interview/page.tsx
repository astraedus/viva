'use client';

import { useCallback, useEffect, useRef, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

import AudioVisualizer from '@/components/AudioVisualizer';
import FeedbackOverlay, { FeedbackData } from '@/components/FeedbackOverlay';
import VideoFeed, { VideoFeedHandle } from '@/components/VideoFeed';
import { VivaWebSocket, PcmPlayer, createAudioProcessorUrl } from '@/lib/websocket';
import { startFrameCapture } from '@/lib/vision';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface InterviewMessage {
  id: string;
  role: 'coach' | 'system';
  text: string;
  timestamp: Date;
}

type ConnectionStatus = 'idle' | 'connecting' | 'connected' | 'disconnected' | 'error';

function InterviewPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session');

  // Refs
  const videoFeedRef = useRef<VideoFeedHandle | null>(null);
  const wsRef = useRef<VivaWebSocket | null>(null);
  const playerRef = useRef<PcmPlayer | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const stopFrameCaptureRef = useRef<(() => void) | null>(null);

  // State
  const [status, setStatus] = useState<ConnectionStatus>('idle');
  const [messages, setMessages] = useState<InterviewMessage[]>([]);
  const [currentQuestion, setCurrentQuestion] = useState<string>('');
  const [questionNumber, setQuestionNumber] = useState(1);
  const [feedback, setFeedback] = useState<FeedbackData | null>(null);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [isMicActive, setIsMicActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState('');
  const [interviewComplete, setInterviewComplete] = useState(false);

  const addMessage = useCallback((role: 'coach' | 'system', text: string) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role, text, timestamp: new Date() },
    ]);
  }, []);

  // Redirect if no session
  useEffect(() => {
    if (!sessionId) {
      router.replace('/');
    }
  }, [sessionId, router]);

  // Initialise WebSocket + audio pipeline
  useEffect(() => {
    if (!sessionId) return;

    const player = new PcmPlayer(24000);
    playerRef.current = player;

    const ws = new VivaWebSocket(sessionId, {
      onConnected: () => {
        setStatus('connected');
        addMessage('system', 'Connected to Viva. Interview starting...');
      },
      onDisconnected: () => {
        setStatus('disconnected');
      },
      onError: (err) => {
        setStatus('error');
        addMessage('system', `Connection error: ${err}`);
      },
      onMessage: (msg) => {
        switch (msg.type) {
          case 'ai_response':
          case 'transcript': {
            const text = msg.payload.text as string;
            addMessage('coach', text);
            break;
          }
          case 'question': {
            const q = msg.payload.question as string;
            const qId = msg.payload.question_id as number;
            setCurrentQuestion(q);
            setQuestionNumber(qId);
            addMessage('coach', q);
            break;
          }
          case 'status': {
            addMessage('system', msg.payload.message as string);
            break;
          }
          case 'error': {
            addMessage('system', `Error: ${msg.payload.message}`);
            break;
          }
          case 'session_end': {
            setInterviewComplete(true);
            addMessage('system', 'Interview complete! Generating your report...');
            break;
          }
        }
      },
      onAudioChunk: (chunk) => {
        player.playChunk(chunk);
      },
    });

    wsRef.current = ws;
    setStatus('connecting');
    ws.connect();

    return () => {
      ws.disconnect();
      player.stop();
    };
  }, [sessionId, addMessage]);

  // Start microphone recording pipeline
  const startMic = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      micStreamRef.current = stream;
      setMicStream(stream);

      const audioCtx = new AudioContext({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;

      const processorUrl = createAudioProcessorUrl();
      await audioCtx.audioWorklet.addModule(processorUrl);
      URL.revokeObjectURL(processorUrl);

      const source = audioCtx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(audioCtx, 'pcm-processor');
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
        wsRef.current?.sendAudio(ev.data);
      };

      source.connect(workletNode);
      setIsMicActive(true);
    } catch (err) {
      addMessage('system', 'Microphone access denied. Please allow microphone and refresh.');
    }
  }, [addMessage]);

  const stopMic = useCallback(() => {
    workletNodeRef.current?.disconnect();
    audioCtxRef.current?.close();
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    setMicStream(null);
    setIsMicActive(false);
  }, []);

  const toggleMic = useCallback(() => {
    if (isMicActive) {
      stopMic();
      wsRef.current?.sendBargeIn();
    } else {
      startMic();
    }
  }, [isMicActive, startMic, stopMic]);

  // Start frame capture once camera is ready
  const handleCameraReady = useCallback(() => {
    if (!sessionId) return;
    const videoEl = videoFeedRef.current?.videoEl;
    if (!videoEl) return;

    const stop = startFrameCapture(
      videoEl,
      sessionId,
      (result) => {
        setFeedback({
          eye_contact: result.eye_contact,
          posture: result.posture,
          expression: result.expression,
          tips: result.tips,
          confidence_score: result.confidence_score,
        });
      },
      (err) => console.warn('[FrameCapture]', err),
      2000,
    );
    stopFrameCaptureRef.current = stop;
  }, [sessionId]);

  // Cleanup frame capture on unmount
  useEffect(() => {
    return () => {
      stopFrameCaptureRef.current?.();
    };
  }, []);

  // Submit current answer for scoring
  const submitAnswer = useCallback(async () => {
    if (!sessionId || !transcript) return;
    try {
      const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/score-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ transcript }),
      });
      const data = await res.json();
      if (data.interview_complete) {
        setInterviewComplete(true);
        addMessage('system', 'All questions answered! Interview complete.');
      } else if (data.next_question) {
        setCurrentQuestion(data.next_question);
        setQuestionNumber((n) => n + 1);
        addMessage('coach', data.next_question);
      }
      setTranscript('');
    } catch (err) {
      addMessage('system', 'Failed to submit answer. Please try again.');
    }
  }, [sessionId, transcript, addMessage]);

  const goToReport = useCallback(() => {
    router.push(`/report?session=${sessionId}`);
  }, [router, sessionId]);

  const statusColor: Record<ConnectionStatus, string> = {
    idle: 'bg-neutral-500',
    connecting: 'bg-amber-400 animate-pulse',
    connected: 'bg-emerald-400',
    disconnected: 'bg-red-500',
    error: 'bg-red-500',
  };

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-neutral-800 bg-neutral-900/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold text-emerald-400">Viva</span>
          <div className="flex items-center gap-1.5 text-xs text-neutral-400">
            <span className={`w-2 h-2 rounded-full ${statusColor[status]}`} />
            <span className="capitalize">{status}</span>
          </div>
        </div>

        <div className="text-sm text-neutral-400">
          Question <span className="text-white font-semibold">{questionNumber}</span>
        </div>

        <button
          onClick={() => router.push('/')}
          className="text-xs text-neutral-500 hover:text-neutral-300 transition"
        >
          Exit
        </button>
      </header>

      {/* Main layout */}
      <div className="flex-1 flex gap-0 overflow-hidden">
        {/* Left panel — camera + visualizer */}
        <aside className="w-72 flex flex-col gap-3 p-4 border-r border-neutral-800 bg-neutral-900/40">
          <VideoFeed
            ref={videoFeedRef}
            onStreamReady={handleCameraReady}
            onError={(err) => setCameraError(err.message)}
            className="aspect-video"
          />

          {cameraError && (
            <div className="text-xs text-red-400 bg-red-900/20 border border-red-500/30 rounded-lg p-2">
              Camera: {cameraError}
            </div>
          )}

          <div className="bg-neutral-900 border border-neutral-700 rounded-xl p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-neutral-400 uppercase tracking-wide">Microphone</span>
              <button
                onClick={toggleMic}
                className={`text-xs px-2.5 py-1 rounded-full font-medium transition ${
                  isMicActive
                    ? 'bg-red-500/20 border border-red-500/40 text-red-300 hover:bg-red-500/30'
                    : 'bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/30'
                }`}
              >
                {isMicActive ? 'Mute' : 'Unmute'}
              </button>
            </div>
            <AudioVisualizer stream={micStream} active={isMicActive} bars={24} />
          </div>
        </aside>

        {/* Centre — interview chat */}
        <main className="flex-1 flex flex-col overflow-hidden">
          {/* Question banner */}
          {currentQuestion && (
            <div className="px-6 py-4 border-b border-neutral-800 bg-neutral-900/60">
              <p className="text-xs text-neutral-500 uppercase tracking-wide mb-1">
                Current Question
              </p>
              <p className="text-base font-medium text-neutral-100 leading-snug">
                {currentQuestion}
              </p>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            {messages.length === 0 && (
              <div className="flex items-center justify-center h-full">
                <p className="text-neutral-600 text-sm italic">
                  Waiting for interview to begin...
                </p>
              </div>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === 'system' ? 'justify-center' : ''}`}
              >
                {msg.role === 'coach' && (
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-xs font-bold text-white shrink-0">
                    V
                  </div>
                )}
                <div
                  className={
                    msg.role === 'system'
                      ? 'text-xs text-neutral-500 italic'
                      : 'bg-neutral-800 border border-neutral-700 rounded-xl px-4 py-3 text-sm text-neutral-100 max-w-xl leading-relaxed'
                  }
                >
                  {msg.text}
                </div>
              </div>
            ))}
          </div>

          {/* Answer input + controls */}
          <div className="px-6 py-4 border-t border-neutral-800 bg-neutral-900/60">
            {interviewComplete ? (
              <div className="flex items-center gap-4">
                <p className="text-sm text-emerald-400 font-medium">Interview complete!</p>
                <button
                  onClick={goToReport}
                  className="px-6 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-sm font-semibold rounded-xl hover:from-emerald-400 hover:to-teal-400 transition"
                >
                  View Report
                </button>
              </div>
            ) : (
              <div className="flex gap-3 items-end">
                <textarea
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                  placeholder="Type your answer here (or speak using the microphone above)..."
                  rows={3}
                  className="flex-1 bg-neutral-800 border border-neutral-600 rounded-xl px-4 py-3 text-sm text-neutral-100 placeholder-neutral-500 resize-none focus:outline-none focus:border-emerald-500 transition"
                />
                <button
                  onClick={submitAnswer}
                  disabled={!transcript.trim()}
                  className="px-5 py-3 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold rounded-xl transition disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
                >
                  Submit
                </button>
              </div>
            )}
          </div>
        </main>

        {/* Right panel — feedback overlay */}
        <aside className="w-64 p-4 border-l border-neutral-800 bg-neutral-900/40 overflow-y-auto">
          <FeedbackOverlay feedback={feedback} className="h-full" />
        </aside>
      </div>
    </div>
  );
}

export default function InterviewPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <p className="text-neutral-400">Loading interview session...</p>
      </div>
    }>
      <InterviewPageInner />
    </Suspense>
  );
}
