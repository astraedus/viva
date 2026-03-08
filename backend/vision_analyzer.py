"""Camera frame analysis via Gemini Vision API.

Sends JPEG frames to gemini-2.0-flash and returns structured body-language
analysis. Falls back to mock data when GOOGLE_API_KEY is not configured.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Optional

from models import BodyLanguageAnalysis, ExpressionType, PostureType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mock data — used when no API key is available
# ---------------------------------------------------------------------------

_MOCK_ANALYSES = [
    BodyLanguageAnalysis(
        eye_contact=True,
        posture=PostureType.upright,
        expression=ExpressionType.confident,
        tips=["Good eye contact!", "Smile naturally to appear more approachable."],
        confidence_score=0.82,
    ),
    BodyLanguageAnalysis(
        eye_contact=False,
        posture=PostureType.slouched,
        expression=ExpressionType.nervous,
        tips=[
            "Try to look directly at the camera lens.",
            "Sit up straight — posture projects confidence.",
            "Take a breath before answering to settle nerves.",
        ],
        confidence_score=0.45,
    ),
    BodyLanguageAnalysis(
        eye_contact=True,
        posture=PostureType.leaning_forward,
        expression=ExpressionType.engaged,
        tips=["Great engagement! Lean forward slightly to show interest."],
        confidence_score=0.88,
    ),
]

_mock_cycle_index = 0


def _get_mock_analysis() -> BodyLanguageAnalysis:
    global _mock_cycle_index
    result = _MOCK_ANALYSES[_mock_cycle_index % len(_MOCK_ANALYSES)]
    _mock_cycle_index += 1
    return result


# ---------------------------------------------------------------------------
# Real Gemini Vision analysis
# ---------------------------------------------------------------------------

_VISION_PROMPT = """You are analyzing a webcam frame from a job interview.
Evaluate the candidate's body language and return a JSON object with EXACTLY these fields:
{
  "eye_contact": boolean,          // true if looking at camera
  "posture": "upright" | "slouched" | "leaning_forward" | "leaning_back",
  "expression": "neutral" | "confident" | "nervous" | "engaged" | "distracted",
  "tips": ["tip1", "tip2"],        // 1-3 actionable tips, empty if all good
  "confidence_score": float        // 0.0 to 1.0
}
Return ONLY the JSON, no markdown, no extra text."""


async def analyze_frame(frame_b64: str, api_key: Optional[str] = None) -> BodyLanguageAnalysis:
    """Analyze a base64-encoded JPEG frame for body language.

    If GOOGLE_API_KEY is not set (or api_key not supplied), returns mock data.
    """
    key = api_key or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        logger.info("No GOOGLE_API_KEY — returning mock body language analysis")
        return _get_mock_analysis()

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=base64.b64decode(frame_b64),
                    mime_type="image/jpeg",
                ),
                _VISION_PROMPT,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        raw = response.text.strip()
        data = json.loads(raw)
        return BodyLanguageAnalysis(
            eye_contact=data["eye_contact"],
            posture=PostureType(data["posture"]),
            expression=ExpressionType(data["expression"]),
            tips=data.get("tips", []),
            confidence_score=float(data["confidence_score"]),
        )

    except Exception as exc:
        logger.warning("Vision API error (%s) -- falling back to mock", exc)
        return _get_mock_analysis()
