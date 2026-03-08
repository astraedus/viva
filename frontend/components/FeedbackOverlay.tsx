'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState } from 'react';

export interface FeedbackData {
  eye_contact: boolean;
  posture: string;
  expression: string;
  tips: string[];
  confidence_score: number;
  filler_word_count?: number;
}

interface FeedbackOverlayProps {
  feedback: FeedbackData | null;
  className?: string;
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 75 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-500';

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-neutral-300">
        <span>{label}</span>
        <span className="font-semibold text-white">{pct}%</span>
      </div>
      <div className="h-1.5 bg-neutral-700 rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
}

function PostureIcon({ posture }: { posture: string }) {
  const icons: Record<string, string> = {
    upright: 'good',
    slouched: 'poor',
    leaning_forward: 'ok',
    leaning_back: 'ok',
  };
  const label = icons[posture] ?? 'ok';
  const colors: Record<string, string> = {
    good: 'text-emerald-400',
    ok: 'text-amber-400',
    poor: 'text-red-400',
  };
  return (
    <span className={`text-xs font-medium ${colors[label] ?? 'text-neutral-300'}`}>
      {posture.replace(/_/g, ' ')}
    </span>
  );
}

/**
 * FeedbackOverlay — sidebar panel showing real-time coaching cues.
 *
 * Animates in/out as new feedback arrives from the vision endpoint.
 * Uses framer-motion for smooth transitions (add to package.json if needed).
 */
export default function FeedbackOverlay({ feedback, className = '' }: FeedbackOverlayProps) {
  const [prevTips, setPrevTips] = useState<string[]>([]);

  useEffect(() => {
    if (feedback?.tips?.length) {
      setPrevTips(feedback.tips);
    }
  }, [feedback]);

  const tips = feedback?.tips?.length ? feedback.tips : prevTips;

  return (
    <div
      className={`flex flex-col gap-4 p-4 bg-neutral-900/90 backdrop-blur-sm border border-neutral-700 rounded-xl ${className}`}
    >
      <h3 className="text-sm font-semibold text-neutral-100 tracking-wide uppercase">
        Live Coaching
      </h3>

      {feedback ? (
        <>
          {/* Confidence score */}
          <ScoreBar label="Confidence" value={feedback.confidence_score} />

          {/* Eye contact */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-neutral-400">Eye Contact</span>
            <span
              className={`text-xs font-medium ${feedback.eye_contact ? 'text-emerald-400' : 'text-red-400'}`}
            >
              {feedback.eye_contact ? 'Good' : 'Improve'}
            </span>
          </div>

          {/* Posture */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-neutral-400">Posture</span>
            <PostureIcon posture={feedback.posture} />
          </div>

          {/* Expression */}
          <div className="flex items-center justify-between">
            <span className="text-xs text-neutral-400">Expression</span>
            <span className="text-xs font-medium text-neutral-200 capitalize">
              {feedback.expression}
            </span>
          </div>

          {/* Filler words */}
          {feedback.filler_word_count !== undefined && (
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-400">Filler Words</span>
              <span
                className={`text-xs font-medium ${
                  feedback.filler_word_count > 5
                    ? 'text-red-400'
                    : feedback.filler_word_count > 2
                    ? 'text-amber-400'
                    : 'text-emerald-400'
                }`}
              >
                {feedback.filler_word_count}
              </span>
            </div>
          )}

          <div className="border-t border-neutral-700 pt-3 space-y-2">
            <span className="text-xs text-neutral-500 uppercase tracking-wide">Tips</span>
            <AnimatePresence mode="popLayout">
              {tips.map((tip, i) => (
                <motion.div
                  key={tip}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 8 }}
                  transition={{ delay: i * 0.05 }}
                  className="flex gap-2 text-xs text-neutral-200 leading-snug"
                >
                  <span className="text-emerald-400 mt-0.5 shrink-0">+</span>
                  <span>{tip}</span>
                </motion.div>
              ))}
            </AnimatePresence>
            {tips.length === 0 && (
              <p className="text-xs text-neutral-500 italic">Waiting for camera data...</p>
            )}
          </div>
        </>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-neutral-500 italic text-center">
            Body language analysis will appear once your camera is active.
          </p>
        </div>
      )}
    </div>
  );
}
