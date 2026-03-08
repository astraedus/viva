'use client';

import { useEffect, useRef } from 'react';

interface AudioVisualizerProps {
  /** Live MediaStream from getUserMedia */
  stream: MediaStream | null;
  /** Whether user is currently speaking / being recorded */
  active?: boolean;
  /** Bar count */
  bars?: number;
  className?: string;
}

/**
 * AudioVisualizer — renders a real-time frequency bar chart from a MediaStream.
 *
 * Uses the Web Audio API AnalyserNode — no extra dependencies required.
 */
export default function AudioVisualizer({
  stream,
  active = true,
  bars = 32,
  className = '',
}: AudioVisualizerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animRef = useRef<number | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);

  useEffect(() => {
    if (!stream || !active) {
      // Draw idle state
      drawIdle();
      return;
    }

    const audioCtx = new AudioContext();
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 128;
    analyser.smoothingTimeConstant = 0.8;

    const source = audioCtx.createMediaStreamSource(stream);
    source.connect(analyser);

    ctxRef.current = audioCtx;
    analyserRef.current = analyser;
    sourceRef.current = source;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    function draw() {
      const canvas = canvasRef.current;
      if (!canvas) return;

      analyser.getByteFrequencyData(dataArray);

      const ctx2d = canvas.getContext('2d');
      if (!ctx2d) return;

      const { width, height } = canvas;
      ctx2d.clearRect(0, 0, width, height);

      const barWidth = (width / bars) * 0.8;
      const gap = (width / bars) * 0.2;

      for (let i = 0; i < bars; i++) {
        const dataIndex = Math.floor((i / bars) * dataArray.length);
        const value = dataArray[dataIndex] / 255;
        const barHeight = Math.max(3, value * height * 0.9);

        const x = i * (barWidth + gap);
        const y = height - barHeight;

        // Gradient: emerald at top, teal at bottom
        const grad = ctx2d.createLinearGradient(0, y, 0, height);
        grad.addColorStop(0, `rgba(52, 211, 153, ${0.5 + value * 0.5})`); // emerald-400
        grad.addColorStop(1, `rgba(20, 184, 166, ${0.3 + value * 0.3})`); // teal-500

        ctx2d.fillStyle = grad;
        ctx2d.beginPath();
        ctx2d.roundRect(x, y, barWidth, barHeight, 2);
        ctx2d.fill();
      }

      animRef.current = requestAnimationFrame(draw);
    }

    draw();

    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
      source.disconnect();
      audioCtx.close();
    };
  }, [stream, active, bars]);

  function drawIdle() {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx2d = canvas.getContext('2d');
    if (!ctx2d) return;

    const { width, height } = canvas;
    ctx2d.clearRect(0, 0, width, height);

    const barWidth = (width / bars) * 0.8;
    const gap = (width / bars) * 0.2;

    for (let i = 0; i < bars; i++) {
      const x = i * (barWidth + gap);
      const barHeight = 3;
      const y = height - barHeight;
      ctx2d.fillStyle = 'rgba(100,116,139,0.4)'; // slate-500
      ctx2d.beginPath();
      ctx2d.roundRect(x, y, barWidth, barHeight, 2);
      ctx2d.fill();
    }
  }

  return (
    <canvas
      ref={canvasRef}
      width={300}
      height={60}
      className={`w-full ${className}`}
      aria-label="Audio level visualizer"
    />
  );
}
