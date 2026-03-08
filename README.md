# Viva — Real-Time AI Interview Coach

Viva is a full-stack application that provides real-time AI coaching during job interviews. It combines Google Gemini's Live audio API with Vision AI to give candidates instant feedback on both their verbal answers and body language.

## Features

- **Live audio conversation** — bidirectional audio streaming via Gemini Live API (gemini-2.5-flash-native-audio-preview)
- **Body language coaching** — periodic webcam frame analysis via Gemini Vision (gemini-2.0-flash), updated every 2 seconds
- **Speech pattern tracking** — filler word detection, pace analysis, confidence scoring
- **Answer scoring** — relevance, clarity, and depth scores per question
- **Post-interview report** — full scorecard with per-question breakdown and aggregate stats
- **Mock mode** — runs fully without a Google API key for local development

## Architecture

```
frontend (Next.js 14)          backend (FastAPI)
  |                               |
  |-- WebSocket /ws/{id} -------> Gemini Live API
  |                               (gemini-2.5-flash-native-audio-preview)
  |
  |-- POST /api/analyze-frame --> Gemini Vision API
                                  (gemini-2.0-flash)
```

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
python main.py
```

Server runs at http://localhost:8000. API docs at http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

App runs at http://localhost:3000.

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_API_KEY` | Optional* | Google AI API key for Gemini. Without it, the app runs in mock mode. |
| `HOST` | No | Server host (default: `0.0.0.0`) |
| `PORT` | No | Server port (default: `8000`) |

*Without `GOOGLE_API_KEY`, all Gemini calls return realistic mock data. The app is fully functional in this mode.

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Backend REST API URL |
| `NEXT_PUBLIC_WS_URL` | `ws://localhost:8000` | Backend WebSocket URL |

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/sessions` | Create a new interview session |
| `GET` | `/api/sessions/{id}` | Get session state |
| `GET` | `/api/sessions/{id}/report` | Get post-interview scorecard |
| `DELETE` | `/api/sessions/{id}` | End a session |
| `POST` | `/api/analyze-frame` | Analyze a camera frame for body language |
| `POST` | `/api/sessions/{id}/score-answer` | Score current answer, get next question |
| `WS` | `/ws/{session_id}` | Bidirectional audio stream |

## WebSocket Protocol

### Client to Server

Binary frames: raw PCM audio (16-bit, 16kHz, mono, little-endian)

JSON frames:
```json
{ "type": "barge_in", "payload": {} }
{ "type": "status", "payload": { "message": "..." } }
```

### Server to Client

Binary frames: raw PCM audio from Gemini (16-bit, 24kHz, mono)

JSON frames:
```json
{ "type": "ai_response", "payload": { "text": "..." } }
{ "type": "question", "payload": { "question": "...", "question_id": 1 } }
{ "type": "status", "payload": { "message": "..." } }
{ "type": "error", "payload": { "message": "..." } }
{ "type": "session_end", "payload": {} }
```

## ADK Agent Tools

The backend ADK agent (`backend/agent.py`) exposes four tools:

| Tool | Description |
|------|-------------|
| `analyze_body_language` | Interprets a natural-language frame description into coaching tips |
| `track_speech_patterns` | Detects filler words and estimates speaking pace from a transcript |
| `score_answer` | Scores a candidate's answer on relevance, clarity, and depth |
| `generate_next_question` | Selects the next question based on role, difficulty, and weak areas |

## Roadmap

- [ ] Wire up real Gemini Live API calls in `live_session.py`
- [ ] Wire up real Gemini Vision calls in `vision_analyzer.py`
- [ ] Real-time transcript display from Gemini speech-to-text
- [ ] Custom question bank upload
- [ ] Session recording and playback
- [ ] Supabase persistence for sessions and reports
- [ ] Deployment: backend on Cloud Run, frontend on Vercel

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Framer Motion |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| AI | Google Gemini Live API, Gemini Vision API, Google ADK |
| Audio | Web Audio API (AudioWorklet), PCM streaming |
