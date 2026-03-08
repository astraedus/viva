"""Pydantic models for Viva interview coach."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class ExpressionType(str, Enum):
    neutral = "neutral"
    confident = "confident"
    nervous = "nervous"
    engaged = "engaged"
    distracted = "distracted"


class PostureType(str, Enum):
    upright = "upright"
    slouched = "slouched"
    leaning_forward = "leaning_forward"
    leaning_back = "leaning_back"


# ---------------------------------------------------------------------------
# Interview session models
# ---------------------------------------------------------------------------

class InterviewConfig(BaseModel):
    role: str = Field(..., description="Target job role, e.g. 'Software Engineer'")
    industry: str = Field(..., description="Industry, e.g. 'Technology'")
    difficulty: Difficulty = Difficulty.medium
    num_questions: int = Field(default=5, ge=1, le=20)


class SpeechPatterns(BaseModel):
    filler_word_count: int = 0
    words_per_minute: Optional[float] = None
    pause_count: int = 0
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class AnswerScore(BaseModel):
    relevance: float = Field(..., ge=0.0, le=10.0)
    clarity: float = Field(..., ge=0.0, le=10.0)
    depth: float = Field(..., ge=0.0, le=10.0)
    overall: float = Field(..., ge=0.0, le=10.0)
    feedback: str
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class BodyLanguageAnalysis(BaseModel):
    eye_contact: bool = True
    posture: PostureType = PostureType.upright
    expression: ExpressionType = ExpressionType.neutral
    tips: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)


class QuestionEntry(BaseModel):
    question_id: int
    question_text: str
    answer_transcript: str = ""
    score: Optional[AnswerScore] = None
    body_language: Optional[BodyLanguageAnalysis] = None
    speech_patterns: Optional[SpeechPatterns] = None


class InterviewSession(BaseModel):
    session_id: str
    config: InterviewConfig
    questions: list[QuestionEntry] = Field(default_factory=list)
    current_question_index: int = 0
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    overall_score: Optional[float] = None
    summary_feedback: str = ""


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------

class AnalyzeFrameRequest(BaseModel):
    session_id: str
    frame_data: str = Field(..., description="Base64-encoded JPEG image")


class AnalyzeFrameResponse(BaseModel):
    eye_contact: bool
    posture: str
    expression: str
    tips: list[str]
    confidence_score: float


class StartSessionRequest(BaseModel):
    config: InterviewConfig


class StartSessionResponse(BaseModel):
    session_id: str
    first_question: str


class SessionReportResponse(BaseModel):
    session_id: str
    config: InterviewConfig
    questions: list[QuestionEntry]
    overall_score: float
    summary_feedback: str
    speech_patterns_aggregate: SpeechPatterns


# ---------------------------------------------------------------------------
# WebSocket message models
# ---------------------------------------------------------------------------

class WSMessageType(str, Enum):
    audio_chunk = "audio_chunk"
    transcript = "transcript"
    ai_response = "ai_response"
    question = "question"
    session_end = "session_end"
    error = "error"
    barge_in = "barge_in"
    status = "status"


class WSMessage(BaseModel):
    type: WSMessageType
    payload: dict = Field(default_factory=dict)
