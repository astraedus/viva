'use client';

import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';

interface VideoFeedProps {
  /** Called once the camera stream is active */
  onStreamReady?: (stream: MediaStream) => void;
  /** Called if camera access fails */
  onError?: (err: Error) => void;
  className?: string;
  /** Mirror the video (default true for front camera feel) */
  mirror?: boolean;
}

export interface VideoFeedHandle {
  videoEl: HTMLVideoElement | null;
  getStream: () => MediaStream | null;
}

/**
 * VideoFeed — renders the webcam feed in a styled container.
 *
 * Exposes a ref so the parent can access the raw <video> element for
 * canvas frame capture (see lib/vision.ts).
 */
const VideoFeed = forwardRef<VideoFeedHandle, VideoFeedProps>(
  ({ onStreamReady, onError, className = '', mirror = true }, ref) => {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const streamRef = useRef<MediaStream | null>(null);

    useImperativeHandle(ref, () => ({
      videoEl: videoRef.current,
      getStream: () => streamRef.current,
    }));

    useEffect(() => {
      let cancelled = false;

      async function initCamera() {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            video: {
              width: { ideal: 1280 },
              height: { ideal: 720 },
              facingMode: 'user',
            },
            audio: false,
          });

          if (cancelled) {
            stream.getTracks().forEach((t) => t.stop());
            return;
          }

          streamRef.current = stream;

          if (videoRef.current) {
            videoRef.current.srcObject = stream;
            await videoRef.current.play();
          }

          onStreamReady?.(stream);
        } catch (err) {
          if (!cancelled) {
            onError?.(err instanceof Error ? err : new Error('Camera access denied'));
          }
        }
      }

      initCamera();

      return () => {
        cancelled = true;
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        if (videoRef.current) {
          videoRef.current.srcObject = null;
        }
      };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    return (
      <div
        className={`relative overflow-hidden rounded-xl bg-neutral-900 border border-neutral-700 ${className}`}
      >
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className={`w-full h-full object-cover ${mirror ? 'scale-x-[-1]' : ''}`}
        />

        {/* Corner indicators */}
        <div className="absolute inset-0 pointer-events-none">
          {/* Top-left corner */}
          <div className="absolute top-2 left-2 w-5 h-5 border-t-2 border-l-2 border-emerald-400/70 rounded-tl" />
          {/* Top-right corner */}
          <div className="absolute top-2 right-2 w-5 h-5 border-t-2 border-r-2 border-emerald-400/70 rounded-tr" />
          {/* Bottom-left corner */}
          <div className="absolute bottom-2 left-2 w-5 h-5 border-b-2 border-l-2 border-emerald-400/70 rounded-bl" />
          {/* Bottom-right corner */}
          <div className="absolute bottom-2 right-2 w-5 h-5 border-b-2 border-r-2 border-emerald-400/70 rounded-br" />
        </div>

        {/* Live badge */}
        <div className="absolute top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-black/60 backdrop-blur-sm rounded-full px-2.5 py-1">
          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          <span className="text-white text-xs font-medium tracking-wide">LIVE</span>
        </div>
      </div>
    );
  },
);

VideoFeed.displayName = 'VideoFeed';

export default VideoFeed;
