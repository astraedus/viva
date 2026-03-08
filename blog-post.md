# Building Viva: A Real-Time AI Interview Coach with Gemini Live API

**TL;DR**: I built Viva, a real-time AI interview coach that listens to your answers via bidirectional audio streaming and watches your body language through your webcam — all powered by Google's Gemini Live API and Vision API, deployed on Cloud Run.

## The Problem

Job seekers practice interviews alone with zero feedback. You can record yourself on your phone and watch it back, but that doesn't tell you about your filler words, pacing, eye contact, or posture in real-time. Human coaches cost $100-300 per session.

## What Viva Does

Viva is a full-stack interview coaching application that provides real-time feedback on both verbal answers and body language:

- **Live audio conversation** — bidirectional audio streaming via Gemini Live API (`gemini-2.5-flash-native-audio-latest`). The AI interviewer asks questions, listens to your answers, and responds naturally. You can interrupt mid-sentence (barge-in).
- **Body language coaching** — webcam frames analyzed every 2 seconds via Gemini Vision (`gemini-2.5-flash`). You get feedback on eye contact, posture, facial expressions, and confidence.
- **Speech pattern tracking** — filler word detection ("um", "uh", "like"), pace analysis, confidence scoring.
- **Answer scoring** — each answer scored on relevance, clarity, and depth.
- **Post-interview report** — full scorecard with per-question breakdown and aggregate stats.

## Architecture

```
Browser (Next.js)                    Google Cloud
  ├─ Mic → AudioWorklet             ┌──────────────────┐
  │   → PCM 16kHz ──WebSocket──►    │  Cloud Run       │
  │                                  │  (FastAPI)       │
  │                                  │       │          │
  │   ◄── PCM 24kHz ◄──────────     │  Gemini Live API │
  │   → PcmPlayer → Speaker         │  (bidi audio)    │
  │                                  │       │          │
  ├─ Camera → JPEG frames           │  Gemini Vision   │
  │   → POST /api/analyze-frame ──► │  (body language)  │
  │                                  │       │          │
  └─ Score/Report ◄──────────────   │  ADK Agent Tools │
                                     └──────────────────┘
```

## The Gemini Live API Pipeline

The core of Viva is the bidirectional audio pipeline. Here's how it works:

1. **Browser captures mic audio** using Web Audio API's AudioWorklet. The worklet converts Float32 samples to 16-bit PCM at 16kHz.

2. **PCM chunks stream over WebSocket** to the FastAPI backend.

3. **Backend forwards to Gemini Live API** using the Google GenAI SDK:

```python
session = await client.aio.live.connect(
    model="gemini-2.5-flash-native-audio-latest",
    config=types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(
            parts=[types.Part(text=system_prompt)]
        ),
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
            )
        ),
    ),
)
```

4. **Gemini responds with audio** — the AI interviewer's voice streams back as 24kHz PCM.

5. **Browser plays the response** through a custom PcmPlayer that buffers and schedules audio chunks for smooth playback.

The barge-in capability is built into the Live API — when the user starts speaking while the AI is talking, the AI naturally stops and listens.

## Body Language Analysis

Every 2 seconds, the frontend captures a JPEG frame from the webcam, downscales to 640x480, and sends it to the backend. The backend uses Gemini Vision to analyze:

- Eye contact (looking at camera vs. looking away)
- Posture (sitting straight, slouching, leaning)
- Facial expressions (smiling, nervous, neutral)
- Hand gestures

The analysis is returned as structured coaching tips that appear as a live overlay on the interview screen.

## ADK Agent Tools

The backend uses Google's Agent Development Kit (ADK) with four tools:

| Tool | Purpose |
|------|---------|
| `analyze_body_language` | Interprets frame descriptions into actionable coaching tips |
| `track_speech_patterns` | Detects filler words and estimates speaking pace |
| `score_answer` | Scores answers on relevance, clarity, and depth (1-10) |
| `generate_next_question` | Selects contextually appropriate follow-up questions |

## Google Cloud Services

| Service | Purpose |
|---------|---------|
| **Cloud Run** | Backend hosting with auto-scaling (0-3 instances) |
| **Cloud Build** | Container image building from Dockerfile |
| **Secret Manager** | Secure API key storage |
| **Generative Language API** | Gemini Live API + Vision API |

## Infrastructure as Code

The entire deployment is automated via a single `deploy.sh` script:

```bash
./deploy.sh
```

This handles: API enablement, Secret Manager setup, container building, Cloud Run deployment, and optional Vercel frontend deployment.

## Mock Mode

Viva runs fully without a Gemini API key — all AI features fall back to realistic mock responses. This makes local development and testing seamless.

## Try It

- **GitHub**: https://github.com/astraedus/viva
- **Live Demo**: https://viva-api-93135657352.us-central1.run.app

Built for the Gemini Live Agent Challenge. #GeminiLiveAgentChallenge

---

*Built with Gemini Live API, Gemini Vision API, Google ADK, FastAPI, Next.js, and Cloud Run.*
