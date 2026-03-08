"""ADK agent definition for Viva interview coach.

The root_agent orchestrates the interview: it asks questions, scores answers,
tracks speech patterns, and synthesises body language feedback into cohesive
coaching tips.

Tools are plain Python functions — the ADK injects them as function-calling
tools into the agent's model context.
"""

from __future__ import annotations

import logging
import os
import random
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def analyze_body_language(frame_description: str) -> dict:
    """Analyze body language from a natural-language description of a webcam frame.

    This tool is called by the agent when it receives a body language summary
    from the vision analyzer. It returns structured coaching feedback.

    Args:
        frame_description: Plain-text description of what the vision API observed
                           (e.g. "candidate is slouching, avoiding eye contact").

    Returns:
        dict with keys: posture, eye_contact, expression, tips, confidence_score
    """
    # TODO: when running with a real API key, this can call Gemini directly
    # for richer reasoning. For now, parse simple keywords from the description.
    desc_lower = frame_description.lower()

    eye_contact = "eye contact" in desc_lower and "avoiding" not in desc_lower
    posture = "slouched" if "slouch" in desc_lower else "upright"
    expression = "nervous" if "nervous" in desc_lower else "neutral"

    tips: list[str] = []
    if not eye_contact:
        tips.append("Look directly at the camera lens — it simulates eye contact with the interviewer.")
    if posture == "slouched":
        tips.append("Sit upright. Good posture signals confidence and engagement.")
    if expression == "nervous":
        tips.append("Take a slow breath before answering — it visibly settles nerves.")
    if not tips:
        tips.append("Great body language! Keep it up.")

    return {
        "posture": posture,
        "eye_contact": eye_contact,
        "expression": expression,
        "tips": tips,
        "confidence_score": round(random.uniform(0.6, 0.95), 2),
    }


def track_speech_patterns(transcript: str) -> dict:
    """Analyze a spoken answer transcript for common interview speech issues.

    Detects filler words (um, uh, like, you know, basically, literally, right),
    estimates speaking pace, and gives a confidence score.

    Args:
        transcript: Raw text transcript of the candidate's spoken answer.

    Returns:
        dict with keys: filler_word_count, words_per_minute, pause_count,
                        confidence_score, flagged_fillers
    """
    FILLERS = {"um", "uh", "like", "you know", "basically", "literally", "right", "so", "i mean"}

    words = transcript.lower().split()
    filler_count = sum(1 for w in words if w.strip(",.?!") in FILLERS)

    # Rough estimate: assume 30-second answers for pace calculation
    word_count = len(words)
    estimated_wpm = round(word_count / 0.5, 1) if word_count > 0 else 0  # 30s = 0.5 min

    # Simple confidence heuristic
    filler_ratio = filler_count / max(word_count, 1)
    confidence = max(0.1, 1.0 - filler_ratio * 3)

    flagged = [w for w in words if w.strip(",.?!") in FILLERS]

    return {
        "filler_word_count": filler_count,
        "words_per_minute": estimated_wpm,
        "pause_count": transcript.count("..."),
        "confidence_score": round(confidence, 2),
        "flagged_fillers": list(set(flagged)),
    }


def score_answer(question: str, answer: str, role: str, difficulty: str) -> dict:
    """Score a candidate's answer to an interview question.

    Evaluates relevance, clarity, and depth. Provides actionable feedback.

    Args:
        question: The interview question that was asked.
        answer: The candidate's answer transcript.
        role: The target job role (e.g. "Software Engineer").
        difficulty: Interview difficulty — "easy", "medium", or "hard".

    Returns:
        dict with keys: relevance, clarity, depth, overall, feedback,
                        strengths, improvements
    """
    try:
        from google import genai
        import json as _json
        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

        prompt = f"""You are an expert interview coach evaluating a candidate's answer.

Role: {role}
Difficulty: {difficulty}
Question: {question}
Answer: {answer}

Score the answer on these dimensions (0-10 scale):
- relevance: How well does the answer address the question?
- clarity: How clearly is the answer communicated?
- depth: How thorough and insightful is the answer?

Also provide:
- overall: Weighted average (relevance 40%, clarity 30%, depth 30%)
- feedback: 1-2 sentence constructive feedback
- strengths: List of 2-3 specific strengths
- improvements: List of 2-3 specific areas to improve

Return ONLY valid JSON with these exact fields. No markdown, no explanation."""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = _json.loads(text)

        return {
            "relevance": float(result.get("relevance", 5.0)),
            "clarity": float(result.get("clarity", 5.0)),
            "depth": float(result.get("depth", 5.0)),
            "overall": float(result.get("overall", 5.0)),
            "feedback": result.get("feedback", "Good attempt. Keep practicing."),
            "strengths": result.get("strengths", ["Addressed the question"]),
            "improvements": result.get("improvements", ["Add more specific examples"]),
        }
    except Exception as e:
        logger.warning("score_answer Gemini call failed: %s — falling back to heuristics", e)
        word_count = len(answer.split())
        if word_count < 30:
            overall = 4.0
        elif word_count < 100:
            overall = 6.5
        else:
            overall = 8.0
        return {
            "relevance": overall,
            "clarity": overall - 0.5,
            "depth": overall - 1.0,
            "overall": overall,
            "feedback": "Answer evaluated. Try to provide more specific examples.",
            "strengths": ["Addressed the question directly"],
            "improvements": ["Include concrete examples from experience"],
        }


def generate_next_question(
    role: str,
    industry: str,
    difficulty: str,
    previous_questions: list[str],
    weak_areas: list[str],
) -> dict:
    """Generate the next interview question tailored to the session context.

    Args:
        role: Target job role.
        industry: Target industry.
        difficulty: "easy", "medium", or "hard".
        previous_questions: List of questions already asked (to avoid repeats).
        weak_areas: Areas where the candidate scored poorly (to probe further).

    Returns:
        dict with keys: question, category, rationale
    """
    # TODO: replace with real Gemini call for dynamic, context-aware questions
    QUESTION_BANK: dict[str, list[tuple[str, str]]] = {
        "easy": [
            ("Tell me about yourself and your background.", "introduction"),
            ("Why are you interested in this role?", "motivation"),
            ("What are your greatest strengths?", "self-assessment"),
            ("Describe your ideal work environment.", "culture-fit"),
            ("Where do you see yourself in five years?", "career-goals"),
        ],
        "medium": [
            ("Describe a challenging project you led. What was your approach?", "leadership"),
            ("Tell me about a time you disagreed with your manager. How did you handle it?", "conflict-resolution"),
            ("How do you prioritise when you have multiple competing deadlines?", "time-management"),
            ("Give an example of a time you failed. What did you learn?", "resilience"),
            ("Describe a situation where you had to influence without authority.", "influence"),
        ],
        "hard": [
            ("Walk me through how you would architect a system serving 10 million users.", "system-design"),
            ("Describe the most technically complex problem you have solved. What trade-offs did you make?", "technical-depth"),
            ("Tell me about a time you made a critical mistake with significant business impact.", "accountability"),
            ("How would you turn around a team with consistently low morale?", "leadership"),
            ("Pitch our company's strategy for entering a new market.", "strategic-thinking"),
        ],
    }

    bank = QUESTION_BANK.get(difficulty, QUESTION_BANK["medium"])
    asked_lower = {q.lower() for q in previous_questions}

    # Prefer questions targeting weak areas
    for q, category in bank:
        if q.lower() not in asked_lower and (not weak_areas or any(w in category for w in weak_areas)):
            return {"question": q, "category": category, "rationale": f"Testing {category} for {role} role"}

    # Fall back to any unasked question
    for q, category in bank:
        if q.lower() not in asked_lower:
            return {"question": q, "category": category, "rationale": f"Standard {difficulty} question"}

    # All questions asked — wrap around
    q, category = bank[0]
    return {"question": q, "category": category, "rationale": "Revisiting earlier topic"}


# ---------------------------------------------------------------------------
# ADK Agent definition
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are Viva, a professional AI interview coach.

Your role:
- Ask interview questions one at a time
- Listen carefully to answers
- Provide specific, actionable feedback after each answer
- Track patterns across the whole interview
- Be encouraging but honest — candidates deserve real feedback
- Adapt question difficulty based on performance

Style:
- Warm, professional, and direct
- Use the candidate's name if known
- Reference their specific answers when giving feedback
- Never repeat the same feedback twice — vary your coaching insights

Always use the STAR method (Situation, Task, Action, Result) as your feedback framework.
"""


def create_agent():
    """Create and return the Viva ADK agent.

    Returns a real ADK agent if google-adk is installed and API key is set,
    otherwise returns a mock agent for local development.
    """
    api_key = os.getenv("GOOGLE_API_KEY", "")

    if not api_key:
        logger.info("No GOOGLE_API_KEY — using mock agent")
        return MockAgent()

    try:
        from google.adk.agents import Agent  # type: ignore

        return Agent(
            name="viva_coach",
            model="gemini-2.5-flash",
            description="AI interview coach that provides real-time feedback",
            instruction=SYSTEM_INSTRUCTION,
            tools=[
                analyze_body_language,
                track_speech_patterns,
                score_answer,
                generate_next_question,
            ],
        )
    except ImportError:
        logger.warning("google-adk not installed — using mock agent")
        return MockAgent()
    except Exception as exc:
        logger.error("Failed to create ADK agent: %s — using mock", exc)
        return MockAgent()


class MockAgent:
    """Lightweight mock for running without the ADK installed."""

    name = "viva_coach_mock"

    def analyze_body_language(self, frame_description: str) -> dict:
        return analyze_body_language(frame_description)

    def track_speech_patterns(self, transcript: str) -> dict:
        return track_speech_patterns(transcript)

    def score_answer(self, question: str, answer: str, role: str, difficulty: str) -> dict:
        return score_answer(question, answer, role, difficulty)

    def generate_next_question(
        self,
        role: str,
        industry: str,
        difficulty: str,
        previous_questions: list[str],
        weak_areas: list[str],
    ) -> dict:
        return generate_next_question(role, industry, difficulty, previous_questions, weak_areas)


# Singleton — imported by main.py
root_agent = create_agent()
