'use client';

import { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface AnswerScore {
  relevance: number;
  clarity: number;
  depth: number;
  overall: number;
  feedback: string;
  strengths: string[];
  improvements: string[];
}

interface QuestionEntry {
  question_id: number;
  question_text: string;
  answer_transcript: string;
  score: AnswerScore | null;
}

interface SessionReport {
  session_id: string;
  config: {
    role: string;
    industry: string;
    difficulty: string;
    num_questions: number;
  };
  questions: QuestionEntry[];
  overall_score: number;
  summary_feedback: string;
  speech_patterns_aggregate: {
    filler_word_count: number;
    words_per_minute: number | null;
    confidence_score: number;
  };
  ai_summary?: string;
}

function ScoreRing({ score }: { score: number }) {
  const pct = (score / 10) * 100;
  const circumference = 2 * Math.PI * 40;
  const strokeDashoffset = circumference - (pct / 100) * circumference;
  const color = score >= 7 ? '#34d399' : score >= 5 ? '#fbbf24' : '#f87171';

  return (
    <div className="relative w-28 h-28">
      <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="40" fill="none" stroke="#262626" strokeWidth="10" />
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1s ease-out' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold text-white">{score.toFixed(1)}</span>
        <span className="text-xs text-neutral-400">/10</span>
      </div>
    </div>
  );
}

function QuestionCard({ entry, index }: { entry: QuestionEntry; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const score = entry.score;

  return (
    <div className="bg-neutral-900 border border-neutral-700 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-neutral-800/50 transition"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <span className="text-xs text-neutral-500 font-medium">Q{index + 1}</span>
          <span className="text-sm text-neutral-100 line-clamp-1">{entry.question_text}</span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {score && (
            <span
              className={`text-sm font-bold ${
                score.overall >= 7
                  ? 'text-emerald-400'
                  : score.overall >= 5
                  ? 'text-amber-400'
                  : 'text-red-400'
              }`}
            >
              {score.overall.toFixed(1)}/10
            </span>
          )}
          <span className="text-neutral-500">{expanded ? '-' : '+'}</span>
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-neutral-800 pt-4">
          {/* Score breakdown */}
          {score ? (
            <>
              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: 'Relevance', val: score.relevance },
                  { label: 'Clarity', val: score.clarity },
                  { label: 'Depth', val: score.depth },
                ].map(({ label, val }) => (
                  <div key={label} className="text-center bg-neutral-800 rounded-lg p-3">
                    <div
                      className={`text-xl font-bold ${
                        val >= 7 ? 'text-emerald-400' : val >= 5 ? 'text-amber-400' : 'text-red-400'
                      }`}
                    >
                      {val.toFixed(1)}
                    </div>
                    <div className="text-xs text-neutral-400 mt-0.5">{label}</div>
                  </div>
                ))}
              </div>

              <p className="text-sm text-neutral-300 leading-relaxed">{score.feedback}</p>

              {score.strengths.length > 0 && (
                <div>
                  <p className="text-xs text-emerald-400 font-semibold uppercase tracking-wide mb-2">
                    Strengths
                  </p>
                  <ul className="space-y-1">
                    {score.strengths.map((s) => (
                      <li key={s} className="text-xs text-neutral-300 flex gap-2">
                        <span className="text-emerald-400">+</span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {score.improvements.length > 0 && (
                <div>
                  <p className="text-xs text-amber-400 font-semibold uppercase tracking-wide mb-2">
                    Improvements
                  </p>
                  <ul className="space-y-1">
                    {score.improvements.map((s) => (
                      <li key={s} className="text-xs text-neutral-300 flex gap-2">
                        <span className="text-amber-400">*</span>
                        {s}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <p className="text-xs text-neutral-500 italic">No score available for this question.</p>
          )}

          {/* Transcript */}
          {entry.answer_transcript && (
            <div>
              <p className="text-xs text-neutral-500 uppercase tracking-wide mb-1">Your Answer</p>
              <p className="text-xs text-neutral-400 bg-neutral-800 rounded-lg p-3 leading-relaxed">
                {entry.answer_transcript}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReportPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('session');

  const [report, setReport] = useState<SessionReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!sessionId) {
      router.replace('/');
      return;
    }

    async function loadReport() {
      try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/report`);
        if (!res.ok) throw new Error(`Report fetch failed: ${res.status}`);
        const data = await res.json();
        setReport(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load report');
      } finally {
        setLoading(false);
      }
    }

    loadReport();
  }, [sessionId, router]);

  if (loading) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="text-center space-y-3">
          <div className="w-10 h-10 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-neutral-400 text-sm">Generating your report...</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="text-center space-y-4">
          <p className="text-red-400">{error || 'Report not found'}</p>
          <button
            onClick={() => router.push('/')}
            className="px-4 py-2 bg-neutral-800 hover:bg-neutral-700 rounded-lg text-sm transition"
          >
            Return Home
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100 py-10 px-4">
      <div className="max-w-3xl mx-auto space-y-8">
        {/* Header */}
        <div className="text-center">
          <div className="inline-flex items-center gap-2 bg-emerald-900/30 border border-emerald-500/30 rounded-full px-4 py-1.5 mb-4">
            <span className="text-emerald-300 text-sm font-medium">Interview Complete</span>
          </div>
          <h1 className="text-4xl font-bold text-white mb-2">Your Scorecard</h1>
          <p className="text-neutral-400">
            {report.config.role} | {report.config.industry} | {report.config.difficulty}
          </p>
        </div>

        {/* Overall score */}
        <div className="bg-neutral-900 border border-neutral-700 rounded-2xl p-8 flex flex-col items-center gap-4">
          <ScoreRing score={report.overall_score} />
          <div className="text-center">
            <p className="text-lg font-semibold text-neutral-100">Overall Performance</p>
            <p className="text-sm text-neutral-400 max-w-sm mt-1 leading-relaxed">
              {report.summary_feedback}
            </p>
          </div>
        </div>

        {/* AI Coaching Summary */}
        {report.ai_summary && (
          <div className="bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border border-emerald-500/30 rounded-xl p-6 mb-8">
            <h3 className="text-emerald-400 font-semibold text-lg mb-3 flex items-center gap-2">
              <span className="w-8 h-8 bg-emerald-500/20 rounded-full flex items-center justify-center text-sm">AI</span>
              Coach's Assessment
            </h3>
            <p className="text-gray-300 leading-relaxed">{report.ai_summary}</p>
          </div>
        )}

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-4">
          {[
            {
              label: 'Questions Answered',
              value: report.questions.length,
              suffix: '',
            },
            {
              label: 'Filler Words',
              value: report.speech_patterns_aggregate.filler_word_count,
              suffix: ' total',
            },
            {
              label: 'Overall Score',
              value: report.overall_score.toFixed(1),
              suffix: '/10',
            },
          ].map(({ label, value, suffix }) => (
            <div
              key={label}
              className="bg-neutral-900 border border-neutral-700 rounded-xl p-5 text-center"
            >
              <div className="text-2xl font-bold text-emerald-400">
                {value}
                <span className="text-base font-normal text-neutral-500">{suffix}</span>
              </div>
              <div className="text-xs text-neutral-400 mt-1">{label}</div>
            </div>
          ))}
        </div>

        {/* Per-question breakdown */}
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-neutral-100">Question Breakdown</h2>
          {report.questions.map((entry, i) => (
            <QuestionCard key={entry.question_id} entry={entry} index={i} />
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-4">
          <button
            onClick={() => router.push('/')}
            className="flex-1 py-3 bg-neutral-800 hover:bg-neutral-700 text-sm font-semibold rounded-xl transition"
          >
            Start New Interview
          </button>
          <button
            onClick={() => window.print()}
            className="px-6 py-3 border border-neutral-600 hover:border-neutral-500 text-sm rounded-xl transition"
          >
            Print / Save PDF
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ReportPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <p className="text-neutral-400">Loading report...</p>
      </div>
    }>
      <ReportPageInner />
    </Suspense>
  );
}
