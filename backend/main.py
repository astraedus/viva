"""Viva — AI Interview Coach Backend.

FastAPI server providing:
  - WebSocket /ws/{session_id}        bidirectional audio streaming via Gemini Live
  - POST     /api/sessions            create a new interview session
  - POST     /api/analyze-frame       analyze a camera frame for body language
  - GET      /api/sessions/{id}       fetch session state
  - GET      /api/sessions/{id}/report  final scorecard after interview ends
  - DELETE   /api/sessions/{id}       end and clean up a session
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent import root_agent
from live_session import create_live_session
from models import (
    AnalyzeFrameRequest,
    AnalyzeFrameResponse,
    InterviewSession,
    QuestionEntry,
    SessionReportResponse,
    SpeechPatterns,
    StartSessionRequest,
    StartSessionResponse,
    WSMessage,
    WSMessageType,
)
from vision_analyzer import analyze_frame

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Viva Interview Coach API",
    version="0.1.0",
    description="Real-time AI-powered interview coaching backend",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# In-memory session store (replace with Redis for production)
# ---------------------------------------------------------------------------
_sessions: dict[str, InterviewSession] = {}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _get_session_or_404(session_id: str) -> InterviewSession:
    session = _sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return session


def _build_system_prompt(session: InterviewSession) -> str:
    cfg = session.config
    return (
        f"You are Viva, an expert interview coach. "
        f"You are conducting a {cfg.difficulty.value} difficulty interview for the role of "
        f"{cfg.role} in the {cfg.industry} industry. "
        f"Ask {cfg.num_questions} questions total, one at a time. "
        f"After each answer, provide brief coaching feedback before asking the next question. "
        f"Be warm, professional, and direct. Use the STAR method framework. "
        f"Start by greeting the candidate and asking the first question."
    )


# ---------------------------------------------------------------------------
# REST Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    """Liveness probe."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/api/sessions", response_model=StartSessionResponse)
async def create_session(request: StartSessionRequest) -> StartSessionResponse:
    """Create a new interview session and return the first question."""
    session_id = str(uuid.uuid4())

    # Generate first question via agent
    first_q_result = root_agent.generate_next_question(
        role=request.config.role,
        industry=request.config.industry,
        difficulty=request.config.difficulty.value,
        previous_questions=[],
        weak_areas=[],
    )
    first_question = first_q_result["question"]

    session = InterviewSession(
        session_id=session_id,
        config=request.config,
        questions=[
            QuestionEntry(question_id=1, question_text=first_question)
        ],
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _sessions[session_id] = session

    logger.info("Created session %s for %s (%s)", session_id, request.config.role, request.config.difficulty.value)
    return StartSessionResponse(session_id=session_id, first_question=first_question)


@app.get("/api/sessions/{session_id}", response_model=InterviewSession)
async def get_session(session_id: str) -> InterviewSession:
    """Fetch current session state."""
    return _get_session_or_404(session_id)


@app.get("/api/sessions/{session_id}/report", response_model=SessionReportResponse)
async def get_report(session_id: str) -> SessionReportResponse:
    """Return post-interview scorecard."""
    session = _get_session_or_404(session_id)

    scored_questions = [q for q in session.questions if q.score is not None]
    if scored_questions:
        overall_score = round(
            sum(q.score.overall for q in scored_questions) / len(scored_questions), 1
        )
    else:
        overall_score = 0.0

    # Aggregate speech patterns
    total_fillers = sum(
        (q.speech_patterns.filler_word_count if q.speech_patterns else 0)
        for q in session.questions
    )
    aggregate_speech = SpeechPatterns(filler_word_count=total_fillers)

    summary = session.summary_feedback or (
        f"You completed {len(session.questions)} question(s) with an overall score of {overall_score}/10. "
        "Review the individual question feedback for detailed improvement areas."
    )

    return SessionReportResponse(
        session_id=session_id,
        config=session.config,
        questions=session.questions,
        overall_score=overall_score,
        summary_feedback=summary,
        speech_patterns_aggregate=aggregate_speech,
    )


@app.delete("/api/sessions/{session_id}")
async def end_session(session_id: str) -> dict:
    """Mark session as ended and clean up."""
    session = _get_session_or_404(session_id)
    session.ended_at = datetime.now(timezone.utc).isoformat()
    # Keep in memory for report retrieval; could TTL-expire later
    logger.info("Session %s ended", session_id)
    return {"status": "ended", "session_id": session_id}


@app.post("/api/analyze-frame", response_model=AnalyzeFrameResponse)
async def analyze_frame_endpoint(request: AnalyzeFrameRequest) -> AnalyzeFrameResponse:
    """Analyze a camera frame for body language cues.

    Expects a base64-encoded JPEG. Returns structured body language analysis.
    """
    # Validate session exists
    _get_session_or_404(request.session_id)

    analysis = await analyze_frame(request.frame_data)

    return AnalyzeFrameResponse(
        eye_contact=analysis.eye_contact,
        posture=analysis.posture.value,
        expression=analysis.expression.value,
        tips=analysis.tips,
        confidence_score=analysis.confidence_score,
    )


@app.post("/api/sessions/{session_id}/score-answer")
async def score_current_answer(session_id: str, body: dict) -> dict:
    """Score a completed answer and advance to next question."""
    session = _get_session_or_404(session_id)
    transcript = body.get("transcript", "")

    if not session.questions:
        raise HTTPException(status_code=400, detail="No active question")

    current_q = session.questions[session.current_question_index]
    current_q.answer_transcript = transcript

    # Score via agent tool
    score_result = root_agent.score_answer(
        question=current_q.question_text,
        answer=transcript,
        role=session.config.role,
        difficulty=session.config.difficulty.value,
    )

    from models import AnswerScore
    current_q.score = AnswerScore(**score_result)

    # Track speech patterns
    speech_result = root_agent.track_speech_patterns(transcript)
    current_q.speech_patterns = SpeechPatterns(
        filler_word_count=speech_result["filler_word_count"],
        words_per_minute=speech_result.get("words_per_minute"),
        confidence_score=speech_result["confidence_score"],
    )

    # Generate next question if interview not complete
    asked = [q.question_text for q in session.questions]
    weak_areas: list[str] = []
    if current_q.score and current_q.score.overall < 6.0:
        weak_areas = ["depth", "clarity"]

    next_q: Optional[str] = None
    if len(session.questions) < session.config.num_questions:
        next_result = root_agent.generate_next_question(
            role=session.config.role,
            industry=session.config.industry,
            difficulty=session.config.difficulty.value,
            previous_questions=asked,
            weak_areas=weak_areas,
        )
        next_q = next_result["question"]
        session.questions.append(
            QuestionEntry(
                question_id=len(session.questions) + 1,
                question_text=next_q,
            )
        )
        session.current_question_index += 1

    return {
        "score": score_result,
        "speech": speech_result,
        "next_question": next_q,
        "interview_complete": next_q is None,
    }


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/{session_id}")
async def websocket_audio_stream(websocket: WebSocket, session_id: str) -> None:
    """Bidirectional audio WebSocket.

    Message protocol (JSON envelope + binary payloads):

    Client -> Server (JSON):
      {"type": "start", "payload": {}}          — begin session
      {"type": "barge_in", "payload": {}}       — user started speaking
      {"type": "audio_chunk", "payload": {}}    — followed immediately by binary frame

    Client -> Server (binary):
      Raw PCM audio bytes (16-bit, 16kHz, mono)

    Server -> Client (JSON):
      {"type": "transcript", "payload": {"text": "..."}}
      {"type": "ai_response", "payload": {"text": "..."}}
      {"type": "question", "payload": {"question": "...", "question_id": N}}
      {"type": "status", "payload": {"message": "..."}}
      {"type": "error", "payload": {"message": "..."}}
      {"type": "session_end", "payload": {}}
    """
    await websocket.accept()
    logger.info("WebSocket connected: session=%s", session_id)

    # Validate session
    session = _sessions.get(session_id)
    if not session:
        await websocket.send_text(
            WSMessage(
                type=WSMessageType.error,
                payload={"message": f"Session {session_id!r} not found"},
            ).model_dump_json()
        )
        await websocket.close(code=4004)
        return

    # Outbound callback: sends audio bytes back to client
    async def send_audio(chunk: bytes) -> None:
        try:
            await websocket.send_bytes(chunk)
        except Exception:
            pass

    # Outbound callback: sends text responses to client
    def send_text_sync(text: str) -> None:
        asyncio.create_task(
            websocket.send_text(
                WSMessage(
                    type=WSMessageType.ai_response,
                    payload={"text": text},
                ).model_dump_json()
            )
        )

    # Build system prompt and create Gemini Live session
    system_prompt = _build_system_prompt(session)
    live = create_live_session(on_audio=send_audio, on_text=send_text_sync)

    # Start live session in background
    live_task = asyncio.create_task(live.start(system_prompt))

    try:
        await websocket.send_text(
            WSMessage(
                type=WSMessageType.status,
                payload={"message": "Connected. Starting interview session..."},
            ).model_dump_json()
        )

        # Send first question
        if session.questions:
            await websocket.send_text(
                WSMessage(
                    type=WSMessageType.question,
                    payload={
                        "question": session.questions[0].question_text,
                        "question_id": 1,
                    },
                ).model_dump_json()
            )

        # Main receive loop
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                # Raw audio chunk — forward to Gemini Live
                await live.send_audio(message["bytes"])

            elif "text" in message and message["text"]:
                data = json.loads(message["text"])
                msg_type = data.get("type")

                if msg_type == "barge_in":
                    await live.barge_in()

                elif msg_type == "status":
                    logger.debug("Client status: %s", data.get("payload"))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
    except Exception as exc:
        logger.error("WebSocket error (session=%s): %s", session_id, exc)
        try:
            await websocket.send_text(
                WSMessage(
                    type=WSMessageType.error,
                    payload={"message": "Internal server error"},
                ).model_dump_json()
            )
        except Exception:
            pass
    finally:
        live_task.cancel()
        await live.close()
        logger.info("Cleaned up session %s", session_id)


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
