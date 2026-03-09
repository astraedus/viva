# Viva — Real-Time AI Interview Coach

Viva is a full-stack application that provides real-time AI coaching during job interviews. It combines Google Gemini's Live audio API with Vision AI to give candidates instant feedback on both their verbal answers and body language.

## Live Demo & Links

| | |
|---|---|
| **Live App** | [viva-kappa-two.vercel.app](https://viva-kappa-two.vercel.app) |
| **Backend API** | [viva-api-93135657352.us-central1.run.app](https://viva-api-93135657352.us-central1.run.app) |
| **Demo Video** | [youtu.be/UYqJ7gFM57A](https://youtu.be/UYqJ7gFM57A) |
| **Blog Post** | [Building Viva: A Real-Time AI Interview Coach with Gemini Live API](https://dev.to/diven_rastdus_c5af27d68f3/building-viva-a-real-time-ai-interview-coach-with-gemini-live-api-2dgf) |
| **DevPost** | [devpost.com/software/viva-real-time-ai-interview-coach](https://devpost.com/software/viva-real-time-ai-interview-coach) |
| **Hackathon** | Gemini Live Agent Challenge 2026 — Live Agents track |

## Features

- **Live audio conversation** — bidirectional audio streaming via Gemini Live API (gemini-2.5-flash-native-audio-preview)
- **Body language coaching** — periodic webcam frame analysis via Gemini Vision (gemini-2.0-flash), updated every 2 seconds
- **Speech pattern tracking** — filler word detection, pace analysis, confidence scoring
- **Answer scoring** — relevance, clarity, and depth scores per question
- **Post-interview report** — full scorecard with per-question breakdown and aggregate stats
- **Mock mode** — runs fully without a Google API key for local development

## Architecture

```
                    ┌─────────────────────────────────────────────┐
                    │              Google Cloud                    │
                    │                                             │
┌──────────┐       │  ┌──────────────┐    ┌───────────────────┐  │
│  Browser  │◄─────┼──┤  Cloud Run   │    │  Gemini Live API  │  │
│           │      │  │  (FastAPI)   │◄──►│  (native-audio)   │  │
│ Next.js   │─ws──►│  │              │    │  Bidirectional    │  │
│ Camera    │      │  │  WebSocket   │    │  Audio Streaming  │  │
│ Mic/Audio │      │  │  Handler     │    └───────────────────┘  │
│ Worklet   │      │  │              │                           │
└──────────┘       │  │  REST API    │    ┌───────────────────┐  │
     │             │  │  /api/*      │───►│  Gemini Vision    │  │
     │ JPEG frames │  │              │    │  (2.5-flash)      │  │
     └─────────────┼──┤  ADK Agent   │    │  Body Language    │  │
                   │  │  Tools       │    │  Analysis         │  │
                   │  └──────────────┘    └───────────────────┘  │
                   │                                             │
                   │  ┌──────────────┐                           │
                   │  │ Secret Mgr   │  API Key Storage          │
                   │  └──────────────┘                           │
                   └─────────────────────────────────────────────┘
```

**Audio Pipeline**: Browser mic (16kHz PCM) -> AudioWorklet -> WebSocket -> Gemini Live API -> 24kHz PCM -> PcmPlayer -> Speaker

**Vision Pipeline**: Camera frame (JPEG) -> REST POST /api/analyze-frame -> Gemini Vision -> Body language coaching tips (every 2s)

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

## Cloud Deployment (IaC)

```bash
# Deploy backend to Cloud Run + frontend to Vercel
export GOOGLE_API_KEY="your-key"
export GOOGLE_CLOUD_PROJECT="your-project-id"
./deploy.sh
```

The `deploy.sh` script automates:
- Enabling required GCP APIs (Cloud Run, Cloud Build, Secret Manager, Generative Language)
- Storing API key in Secret Manager
- Building container image via Cloud Build
- Deploying to Cloud Run with auto-scaling (0-3 instances)
- Deploying frontend to Vercel with backend URL injection

## Google Cloud Services Used

| Service | Purpose |
|---------|---------|
| Cloud Run | Backend hosting (auto-scaling, serverless) |
| Cloud Build | Container image building |
| Secret Manager | API key storage |
| Generative Language API | Gemini Live API + Vision API |

## Roadmap

- [ ] Real-time transcript display from Gemini speech-to-text
- [ ] Custom question bank upload
- [ ] Session recording and playback
- [ ] Cloud Storage for session recordings

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Framer Motion |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| AI | Google Gemini Live API, Gemini Vision API, Google ADK |
| Audio | Web Audio API (AudioWorklet), PCM streaming |
