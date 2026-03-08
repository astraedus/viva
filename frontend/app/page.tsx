'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

const ROLES = [
  'Software Engineer',
  'Product Manager',
  'Data Scientist',
  'UX Designer',
  'Marketing Manager',
  'Sales Representative',
  'Business Analyst',
  'DevOps Engineer',
  'Frontend Engineer',
  'Backend Engineer',
];

const INDUSTRIES = [
  'Technology',
  'Finance',
  'Healthcare',
  'E-commerce',
  'Education',
  'Media & Entertainment',
  'Consulting',
  'Startups',
  'Government',
  'Non-profit',
];

const DIFFICULTIES = [
  {
    value: 'easy',
    label: 'Starter',
    desc: 'Introductory questions — great for practice',
    color: 'border-emerald-500/50 bg-emerald-900/20',
    activeColor: 'border-emerald-400 bg-emerald-900/40 ring-2 ring-emerald-500/30',
  },
  {
    value: 'medium',
    label: 'Professional',
    desc: 'Real-world behavioural & situational questions',
    color: 'border-amber-500/50 bg-amber-900/20',
    activeColor: 'border-amber-400 bg-amber-900/40 ring-2 ring-amber-500/30',
  },
  {
    value: 'hard',
    label: 'Senior',
    desc: 'Deep technical & leadership challenges',
    color: 'border-red-500/50 bg-red-900/20',
    activeColor: 'border-red-400 bg-red-900/40 ring-2 ring-red-500/30',
  },
];

export default function SetupPage() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const [role, setRole] = useState('Software Engineer');
  const [customRole, setCustomRole] = useState('');
  const [industry, setIndustry] = useState('Technology');
  const [difficulty, setDifficulty] = useState('medium');
  const [numQuestions, setNumQuestions] = useState(5);
  const [error, setError] = useState('');

  const finalRole = customRole.trim() || role;

  async function handleStart() {
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config: {
            role: finalRole,
            industry,
            difficulty,
            num_questions: numQuestions,
          },
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }

      const { session_id } = await res.json();
      startTransition(() => {
        router.push(`/interview?session=${session_id}`);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start session');
    }
  }

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center p-6">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 bg-emerald-900/30 border border-emerald-500/30 rounded-full px-4 py-1.5 mb-4">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-emerald-300 text-sm font-medium">AI Interview Coach</span>
        </div>
        <h1 className="text-5xl font-bold tracking-tight mb-3">
          <span className="text-white">Meet </span>
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-teal-300">
            Viva
          </span>
        </h1>
        <p className="text-neutral-400 text-lg max-w-md mx-auto">
          Real-time AI coaching for your next big interview. Practice, refine, and land the job.
        </p>
      </div>

      {/* Setup card */}
      <div className="w-full max-w-xl bg-neutral-900 border border-neutral-700 rounded-2xl p-8 space-y-6">
        {/* Role */}
        <div>
          <label className="block text-sm font-medium text-neutral-300 mb-2">Target Role</label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="w-full bg-neutral-800 border border-neutral-600 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:outline-none focus:border-emerald-500 transition"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={customRole}
            onChange={(e) => setCustomRole(e.target.value)}
            placeholder="Or type a custom role..."
            className="mt-2 w-full bg-neutral-800 border border-neutral-600 rounded-lg px-3 py-2.5 text-sm text-neutral-100 placeholder-neutral-500 focus:outline-none focus:border-emerald-500 transition"
          />
        </div>

        {/* Industry */}
        <div>
          <label className="block text-sm font-medium text-neutral-300 mb-2">Industry</label>
          <select
            value={industry}
            onChange={(e) => setIndustry(e.target.value)}
            className="w-full bg-neutral-800 border border-neutral-600 rounded-lg px-3 py-2.5 text-sm text-neutral-100 focus:outline-none focus:border-emerald-500 transition"
          >
            {INDUSTRIES.map((ind) => (
              <option key={ind} value={ind}>
                {ind}
              </option>
            ))}
          </select>
        </div>

        {/* Difficulty */}
        <div>
          <label className="block text-sm font-medium text-neutral-300 mb-2">Difficulty</label>
          <div className="grid grid-cols-3 gap-3">
            {DIFFICULTIES.map((d) => (
              <button
                key={d.value}
                onClick={() => setDifficulty(d.value)}
                className={`text-left p-3 rounded-xl border transition-all duration-150 ${
                  difficulty === d.value ? d.activeColor : d.color + ' hover:opacity-80'
                }`}
              >
                <div className="text-sm font-semibold text-neutral-100">{d.label}</div>
                <div className="text-xs text-neutral-400 mt-0.5 leading-tight">{d.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Number of questions */}
        <div>
          <label className="block text-sm font-medium text-neutral-300 mb-2">
            Questions: <span className="text-emerald-400 font-bold">{numQuestions}</span>
          </label>
          <input
            type="range"
            min={1}
            max={15}
            value={numQuestions}
            onChange={(e) => setNumQuestions(Number(e.target.value))}
            className="w-full accent-emerald-500"
          />
          <div className="flex justify-between text-xs text-neutral-500 mt-1">
            <span>Quick (1)</span>
            <span>Full (15)</span>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-900/30 border border-red-500/40 rounded-lg px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* CTA */}
        <button
          onClick={handleStart}
          disabled={isPending}
          className="w-full py-3.5 rounded-xl font-semibold text-sm bg-gradient-to-r from-emerald-500 to-teal-500 text-white hover:from-emerald-400 hover:to-teal-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-emerald-900/40"
        >
          {isPending ? 'Starting session...' : 'Start Interview'}
        </button>
      </div>

      {/* Features */}
      <div className="mt-10 grid grid-cols-3 gap-6 max-w-xl w-full text-center">
        {[
          { icon: '🎙', title: 'Real-time audio', desc: 'Powered by Gemini Live API' },
          { icon: '📹', title: 'Body language', desc: 'Vision AI coaching every 2s' },
          { icon: '📊', title: 'Full report', desc: 'Scored feedback after session' },
        ].map((f) => (
          <div key={f.title} className="space-y-1">
            <div className="text-2xl">{f.icon}</div>
            <div className="text-sm font-medium text-neutral-200">{f.title}</div>
            <div className="text-xs text-neutral-500">{f.desc}</div>
          </div>
        ))}
      </div>
    </main>
  );
}
