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

from dotenv import load_dotenv

load_dotenv()
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from agent import root_agent, generate_next_question, score_answer, track_speech_patterns, analyze_body_language
from live_session import create_live_session
from models import (
    AnalyzeFrameRequest,
    AnalyzeFrameResponse,
    AnswerScore,
    BodyLanguageSummary,
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

# Body language frames stored per session: session_id -> list of frame dicts
# Each frame dict: {posture, eye_contact, expression, confidence_score, tips}
_body_language_frames: dict[str, list[dict]] = {}

# Conversation logs from live audio sessions: session_id -> list of {role, text}
_conversation_logs: dict[str, list[dict]] = {}

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
    type_guidance = {
        "behavioral": "Focus on behavioral questions using the STAR method (Situation, Task, Action, Result). Ask about real experiences, soft skills, and interpersonal scenarios.",
        "technical": "Focus on technical questions about system design, coding concepts, architecture, and domain-specific knowledge.",
        "case_study": "Focus on case study questions with business scenarios, problem-solving frameworks, and analytical thinking.",
        "mixed": "Mix behavioral, technical, and case study questions for comprehensive preparation.",
    }
    interview_type = cfg.interview_type.value
    return (
        f"You are Viva, an expert AI interview coach having a natural voice conversation. "
        f"You are conducting a {cfg.difficulty.value} difficulty {interview_type} interview for the role of "
        f"{cfg.role} in the {cfg.industry} industry. "
        f"{type_guidance.get(interview_type, type_guidance['mixed'])} "
        f"Conduct the full interview naturally as a conversation. Ask EXACTLY {cfg.num_questions} question(s) total — no more. "
        f"You have full control of the interview flow: "
        f"ask a question, listen to the answer, give brief constructive feedback. "
        f"If the answer is vague, note it in your feedback but move on — do NOT ask follow-up questions. "
        f"After {cfg.num_questions} question(s), wrap up immediately. "
        f"Be warm, professional, and direct. Keep your responses concise since this is a voice conversation. "
        f"When all questions are covered, wrap up by thanking the candidate and giving a brief overall impression. "
        f"You MUST end your final closing message with the exact words 'best of luck' to signal the interview is over. "
        f"Start by greeting the candidate warmly and asking your first question."
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
    """Create a new interview session.

    For live audio sessions, Gemini generates its own questions from the system
    prompt — no pre-generated question needed.
    """
    session_id = str(uuid.uuid4())

    session = InterviewSession(
        session_id=session_id,
        config=request.config,
        questions=[],
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    _sessions[session_id] = session
    _body_language_frames[session_id] = []

    logger.info("Created session %s for %s (%s)", session_id, request.config.role, request.config.difficulty.value)
    return StartSessionResponse(session_id=session_id)


@app.get("/api/sessions/{session_id}", response_model=InterviewSession)
async def get_session(session_id: str) -> InterviewSession:
    """Fetch current session state."""
    return _get_session_or_404(session_id)


async def score_transcript_questions(
    session: InterviewSession,
    conversation_log: list[dict],
) -> tuple[list[QuestionEntry], float]:
    """Extract Q&A pairs from a live conversation transcript and score each one.

    Returns (scored_questions, overall_score).
    """
    try:
        from google import genai
        from google.genai import types
        import json as _json

        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

        transcript_lines = []
        for entry in conversation_log:
            role_label = "Candidate" if entry["role"] == "user" else "Interviewer"
            transcript_lines.append(f"{role_label}: {entry['text']}")
        conversation_text = "\n".join(transcript_lines)

        prompt = f"""You are an expert interview coach analyzing a completed interview transcript.

Role: {session.config.role}
Industry: {session.config.industry}
Difficulty: {session.config.difficulty.value}
Interview type: {session.config.interview_type.value}

Full conversation transcript:
{conversation_text}

Extract each question-answer pair from this transcript and score the candidate's answers.
For each Q&A pair, provide:
- question: the interviewer's question (paraphrased if needed)
- answer: brief summary of the candidate's answer (1-2 sentences)
- relevance: score 0-10
- clarity: score 0-10
- depth: score 0-10
- overall: weighted average (relevance 40%, clarity 30%, depth 30%)
- feedback: 1-2 sentence constructive feedback
- strengths: list of 1-2 strengths
- improvements: list of 1-2 areas to improve

Return ONLY a JSON array of objects. No markdown, no explanation.
If the candidate didn't answer a question, skip it.
Score at least the questions that were answered."""

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        scored_items = _json.loads(text)

        if not isinstance(scored_items, list):
            scored_items = [scored_items]

        questions: list[QuestionEntry] = []
        total_score = 0.0
        for i, item in enumerate(scored_items):
            score = AnswerScore(
                relevance=min(10.0, max(0.0, float(item.get("relevance", 5.0)))),
                clarity=min(10.0, max(0.0, float(item.get("clarity", 5.0)))),
                depth=min(10.0, max(0.0, float(item.get("depth", 5.0)))),
                overall=min(10.0, max(0.0, float(item.get("overall", 5.0)))),
                feedback=item.get("feedback", ""),
                strengths=item.get("strengths", []),
                improvements=item.get("improvements", []),
            )
            questions.append(QuestionEntry(
                question_id=i + 1,
                question_text=item.get("question", f"Question {i + 1}"),
                answer_transcript=item.get("answer", ""),
                score=score,
            ))
            total_score += score.overall

        overall = round(total_score / len(questions), 1) if questions else 0.0
        return questions, overall

    except Exception as e:
        logger.warning("score_transcript_questions failed: %s", e)
        return [], 0.0


async def generate_report_summary(session, conversation_log: list[dict] | None = None) -> str:
    """Generate AI coaching summary for the interview report.

    Uses the live conversation transcript if available, otherwise falls back
    to scored question data.
    """
    try:
        from google import genai
        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

        # Build context from conversation log (live session) or scored questions
        if conversation_log:
            transcript_lines = []
            for entry in conversation_log:
                role_label = "Candidate" if entry["role"] == "user" else "Interviewer"
                transcript_lines.append(f"{role_label}: {entry['text']}")
            conversation_text = "\n".join(transcript_lines)

            prompt = f"""You are an expert interview coach writing a personalized debrief.

Role applied for: {session.config.role}
Industry: {session.config.industry}
Difficulty: {session.config.difficulty.value}
Interview type: {session.config.interview_type.value}

Full conversation transcript:
{conversation_text}

Write a detailed coaching summary (4-6 sentences). Score the candidate 1-10 overall. Be specific about what they did well and what to improve. Reference specific things they said. Keep it encouraging but honest."""
        else:
            questions_summary = []
            for q in session.questions:
                questions_summary.append(
                    f"Q: {q.question_text}\nScore: {q.score.overall if q.score else 'N/A'}"
                )

            scored_questions = [q for q in session.questions if q.score is not None]
            overall_score = (
                round(sum(q.score.overall for q in scored_questions) / len(scored_questions), 1)
                if scored_questions else 0.0
            )

            prompt = f"""You are an expert interview coach writing a personalized debrief.

Role applied for: {session.config.role}
Industry: {session.config.industry}
Difficulty: {session.config.difficulty.value}
Overall Score: {overall_score}/10

Questions and scores:
{chr(10).join(questions_summary)}

Write a 3-4 sentence coaching summary. Be specific, encouraging but honest. Mention their strongest area and #1 thing to improve. Keep it conversational and motivating."""

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        logger.warning("generate_report_summary failed: %s", e)
        return "Great effort! Review your scores above and focus on areas marked for improvement. Practice with specific examples from your experience."


@app.get("/api/sessions/{session_id}/report", response_model=SessionReportResponse)
async def get_report(session_id: str) -> SessionReportResponse:
    """Return post-interview scorecard."""
    session = _get_session_or_404(session_id)

    # If live audio session with unscored questions, score from conversation transcript
    conv_log = _conversation_logs.get(session_id)
    scored_questions = [q for q in session.questions if q.score is not None]
    if not scored_questions and conv_log and len(conv_log) >= 2:
        logger.info("Scoring %d conversation entries for session %s", len(conv_log), session_id)
        transcript_questions, transcript_score = await score_transcript_questions(session, conv_log)
        if transcript_questions:
            session.questions = transcript_questions
            scored_questions = transcript_questions

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

    ai_summary = await generate_report_summary(session, conversation_log=conv_log)

    # Aggregate body language frames
    body_language_summary: Optional[BodyLanguageSummary] = None
    frames = _body_language_frames.get(session_id, [])
    if frames:
        total = len(frames)
        avg_confidence = sum(f["confidence_score"] for f in frames) / total
        eye_contact_count = sum(1 for f in frames if f["eye_contact"])
        eye_contact_pct = (eye_contact_count / total) * 100.0

        posture_counts: dict[str, int] = {}
        expression_counts: dict[str, int] = {}
        all_tips: list[str] = []
        for f in frames:
            p = f["posture"]
            posture_counts[p] = posture_counts.get(p, 0) + 1
            ex = f["expression"]
            expression_counts[ex] = expression_counts.get(ex, 0) + 1
            all_tips.extend(f.get("tips", []))

        posture_breakdown = {
            p: round((count / total) * 100.0, 1)
            for p, count in posture_counts.items()
        }
        dominant_expression = max(expression_counts, key=lambda k: expression_counts[k])

        # Top 3 most frequent tips
        tip_counts: dict[str, int] = {}
        for tip in all_tips:
            tip_counts[tip] = tip_counts.get(tip, 0) + 1
        top_tips = [tip for tip, _ in sorted(tip_counts.items(), key=lambda x: -x[1])[:3]]

        body_language_summary = BodyLanguageSummary(
            avg_confidence=round(avg_confidence, 2),
            eye_contact_percentage=round(eye_contact_pct, 1),
            posture_breakdown=posture_breakdown,
            dominant_expression=dominant_expression,
            total_frames_analyzed=total,
            tips=top_tips,
        )

    return SessionReportResponse(
        session_id=session_id,
        config=session.config,
        questions=session.questions,
        overall_score=overall_score,
        summary_feedback=summary,
        speech_patterns_aggregate=aggregate_speech,
        ai_summary=ai_summary,
        body_language_summary=body_language_summary,
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

    # Store frame data for body language summary in report
    if request.session_id not in _body_language_frames:
        _body_language_frames[request.session_id] = []
    _body_language_frames[request.session_id].append({
        "posture": analysis.posture.value,
        "eye_contact": analysis.eye_contact,
        "expression": analysis.expression.value,
        "confidence_score": analysis.confidence_score,
        "tips": analysis.tips,
    })

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

    # Score via agent tool (run in thread to avoid blocking event loop)
    score_result = await asyncio.to_thread(
        score_answer,
        question=current_q.question_text,
        answer=transcript,
        role=session.config.role,
        difficulty=session.config.difficulty.value,
    )

    current_q.score = AnswerScore(**score_result)

    # Track speech patterns
    speech_result = await asyncio.to_thread(track_speech_patterns, transcript)
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
        next_result = await asyncio.to_thread(
            generate_next_question,
            role=session.config.role,
            industry=session.config.industry,
            difficulty=session.config.difficulty.value,
            previous_questions=asked,
            weak_areas=weak_areas,
            interview_type=session.config.interview_type.value,
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


@app.post("/api/sessions/{session_id}/end-early")
async def end_interview_early(session_id: str) -> dict:
    """End the interview early and generate a report from whatever questions were answered."""
    session = _get_session_or_404(session_id)

    # Score transcript from conversation log before generating summary
    conv_log = _conversation_logs.get(session_id)
    scored_questions = [q for q in session.questions if q.score is not None]

    if not scored_questions and conv_log and len(conv_log) >= 2:
        logger.info("End-early: scoring %d conversation entries for session %s", len(conv_log), session_id)
        transcript_questions, _ = await score_transcript_questions(session, conv_log)
        if transcript_questions:
            session.questions = transcript_questions
            scored_questions = transcript_questions

    overall_score = (
        round(sum(q.score.overall for q in scored_questions) / len(scored_questions), 1)
        if scored_questions else 0.0
    )

    # Generate AI summary from conversation log or scored questions
    ai_summary = ""
    if conv_log or scored_questions:
        ai_summary = await generate_report_summary(session, conversation_log=conv_log)

    # Store summary on session so report endpoint can use it
    session.summary_feedback = ai_summary

    return {
        "session_id": session_id,
        "questions_answered": len(scored_questions),
        "questions_total": len(session.questions),
        "overall_score": overall_score,
        "ai_summary": ai_summary,
        "ended_early": True,
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

    # Store conversation log continuously so it's always available for reports.
    # This fixes the race condition where session_end fires before finally{} stores it.
    _conversation_logs[session_id] = []

    # Outbound callback: sends AI text responses to client
    def send_text_sync(text: str) -> None:
        _conversation_logs[session_id].append({"role": "ai", "text": text})
        asyncio.create_task(
            websocket.send_text(
                WSMessage(
                    type=WSMessageType.ai_response,
                    payload={"text": text},
                ).model_dump_json()
            )
        )

    # Outbound callback: sends user's speech transcription to client
    def send_input_transcript(text: str) -> None:
        _conversation_logs[session_id].append({"role": "user", "text": text})
        asyncio.create_task(
            websocket.send_text(
                WSMessage(
                    type=WSMessageType.transcript,
                    payload={"text": text},
                ).model_dump_json()
            )
        )

    # Outbound callback: notifies client when Gemini session ends
    def on_gemini_session_end(reason: str) -> None:
        logger.warning("Gemini session ended for %s: %s", session_id, reason)
        is_complete = "completed" in reason.lower()
        asyncio.create_task(
            websocket.send_text(
                WSMessage(
                    type=WSMessageType.session_end if is_complete else WSMessageType.status,
                    payload={"message": f"Interview complete! Generating your report..." if is_complete else f"AI session ended: {reason}"},
                ).model_dump_json()
            )
        )

    # Build system prompt and create Gemini Live session
    # Gemini owns the full conversation flow — no pre-generated questions needed
    system_prompt = _build_system_prompt(session)
    live = create_live_session(
        on_audio=send_audio,
        on_text=send_text_sync,
        on_input_transcript=send_input_transcript,
        on_session_end=on_gemini_session_end,
    )

    # Start live session — Gemini will greet and ask its first question based on the system prompt
    live_task = asyncio.create_task(live.start(system_prompt))

    try:
        await websocket.send_text(
            WSMessage(
                type=WSMessageType.status,
                payload={"message": "Connected. Starting interview session..."},
            ).model_dump_json()
        )

        # Main receive loop
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"]:
                # Raw audio chunk — forward to Gemini Live
                if not hasattr(live, '_audio_count'):
                    live._audio_count = 0
                live._audio_count += 1
                if live._audio_count <= 3 or live._audio_count % 100 == 0:
                    logger.info("Audio chunk #%d from client (%d bytes)", live._audio_count, len(message["bytes"]))
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
        conv_log = _conversation_logs.get(session_id, [])
        if session_id in _sessions and conv_log:
            _sessions[session_id].summary_feedback = ""  # Will be generated in report
        logger.info("Cleaned up session %s (%d conversation entries)", session_id, len(conv_log))


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
