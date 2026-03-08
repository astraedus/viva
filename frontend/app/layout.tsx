import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter' });

export const metadata: Metadata = {
  title: 'Viva — AI Interview Coach',
  description: 'Real-time AI-powered interview coaching with Gemini Live and Vision APIs.',
  keywords: ['interview', 'AI coach', 'Gemini', 'practice', 'career'],
  openGraph: {
    title: 'Viva — AI Interview Coach',
    description: 'Practice interviews with a real-time AI coach powered by Google Gemini.',
    type: 'website',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="antialiased font-sans">{children}</body>
    </html>
  );
}
