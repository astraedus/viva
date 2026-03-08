# DevPost Submission — Viva

## Project Name
Viva — Real-Time AI Interview Coach

## Category
Best Live Agent

## Tagline
Practice interviews with an AI that watches your body language and coaches your speech in real-time

## Description

### Inspiration
Job interviews are high-stakes conversations where preparation is everything — but most people practice alone with zero feedback. Human coaches cost $100-300/session and aren't available on demand. We wanted to build an AI interviewer that could provide the same real-time feedback a human coach would: listening to answers, watching body language, and coaching in the moment.

### What it does
Viva is a real-time AI interview coach that combines bidirectional audio streaming with live webcam analysis:

- **Conducts mock interviews** — the AI asks role-appropriate questions, listens to your answers, and responds naturally via voice
- **Coaches body language** — analyzes webcam frames every 2 seconds for eye contact, posture, and facial expressions
- **Tracks speech patterns** — detects filler words, pacing issues, and confidence level
- **Scores every answer** — relevance, clarity, and depth scores on a 1-10 scale
- **Generates a report card** — post-interview scorecard with per-question breakdown

### How we built it
**Backend**: Python FastAPI on Cloud Run with the Google GenAI SDK. The Gemini Live API (`gemini-2.5-flash-native-audio-latest`) handles bidirectional audio streaming via WebSocket. Gemini Vision (`gemini-2.5-flash`) analyzes webcam frames. Four ADK agent tools handle speech tracking, body language coaching, answer scoring, and question generation.

**Frontend**: Next.js with Web Audio API AudioWorklet for mic capture (16kHz PCM) and a custom PcmPlayer for audio playback (24kHz PCM). Camera feed captured via getUserMedia with periodic JPEG frame extraction.

**Audio pipeline**: Browser mic → AudioWorklet (Float32 → Int16 PCM) → WebSocket → Gemini Live API → 24kHz PCM → PcmPlayer → Speaker. Supports natural barge-in.

**Vision pipeline**: Camera → canvas.toDataURL('image/jpeg') → POST /api/analyze-frame → Gemini Vision → coaching tips overlay (every 2s).

### Challenges we ran into
- Getting the bidirectional audio pipeline to work smoothly with proper sample rate conversion (16kHz mic → 24kHz speaker)
- Handling barge-in gracefully when the user interrupts the AI mid-sentence
- Keeping webcam frame analysis lightweight enough to run every 2 seconds without blocking the audio stream

### Accomplishments that we're proud of
- The Live API connection works seamlessly — you can have a natural voice conversation with interruptions
- Real-time body language feedback appears as an overlay while you're speaking
- The entire system deploys with a single `./deploy.sh` script
- Mock mode works fully without an API key for development

### What we learned
- Gemini Live API's bidirectional streaming is remarkably natural — barge-in works out of the box
- AudioWorklet is essential for low-latency mic capture (ScriptProcessorNode introduces too much delay)
- Webcam analysis at 2-second intervals provides useful feedback without being overwhelming

### What's next for Viva
- Real-time transcript display from Gemini speech-to-text
- Custom question bank upload
- Session recording and playback
- Cloud Storage for session recordings

## Built With
- Google Gemini Live API (gemini-2.5-flash-native-audio-latest)
- Google Gemini Vision API (gemini-2.5-flash)
- Google Agent Development Kit (ADK)
- FastAPI + Uvicorn
- Next.js 14 + React 18 + TypeScript
- Tailwind CSS + Framer Motion
- Web Audio API (AudioWorklet)
- Google Cloud Run
- Google Cloud Build
- Google Secret Manager
- SQLite
- Python 3.12

## Try it out
- GitHub: https://github.com/astraedus/viva
- Live Demo: https://viva-api-93135657352.us-central1.run.app

#GeminiLiveAgentChallenge
