"""Gemini Live API session manager for real-time audio streaming.

Handles bidirectional audio between the FastAPI WebSocket and Gemini Live API
(gemini-2.5-flash-native-audio-preview).

Audio format contract:
- Input (client -> Gemini): PCM 16-bit, 16 kHz, mono, little-endian
- Output (Gemini -> client): PCM 16-bit, 24 kHz, mono, little-endian (Gemini native)

The session manager runs as a background task alongside the WebSocket handler.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator, Callable, Optional

logger = logging.getLogger(__name__)

# Type alias for audio chunk callback
AudioChunkCallback = Callable[[bytes], None]


# ---------------------------------------------------------------------------
# Mock live session — used when GOOGLE_API_KEY is not set
# ---------------------------------------------------------------------------

class MockLiveSession:
    """Simulates Gemini Live responses for local development."""

    MOCK_RESPONSES = [
        b"\x00" * 1024,  # Silence — real impl would be actual PCM audio
    ]

    def __init__(self, on_audio: AudioChunkCallback, on_text: Callable[[str], None], on_input_transcript: Optional[Callable[[str], None]] = None, on_session_end: Optional[Callable[[str], None]] = None):
        self._on_audio = on_audio
        self._on_text = on_text
        self._on_input_transcript = on_input_transcript
        self._on_session_end = on_session_end
        self._active = False
        self._task: Optional[asyncio.Task] = None
        self._turn_count = 0

    async def start(self, system_prompt: str, first_question: str = "") -> None:
        self._active = True
        logger.info("MockLiveSession started (no API key)")
        # Send a greeting immediately
        await asyncio.sleep(0.5)
        self._on_text(
            "Hello! I'm your Viva interview coach. I'm running in demo mode "
            "(no API key configured). Let's begin — tell me about yourself."
        )

    async def send_audio(self, chunk: bytes) -> None:
        """Accept audio from client. In mock mode just echo silence back."""
        if not self._active:
            return
        # Simulate latency + response every ~2 seconds of audio (32000 bytes @ 16kHz/16bit)
        # Real impl: forward to Gemini Live API
        pass

    async def send_text(self, text: str) -> None:
        """Inject text message into the session (for tool results etc.)."""
        if not self._active:
            return
        self._turn_count += 1
        await asyncio.sleep(0.3)
        mock_reply = (
            f"(Mock response #{self._turn_count}) Great answer! "
            "In a real session, Gemini would provide detailed feedback here. "
            "Try to structure your responses using the STAR method."
        )
        self._on_text(mock_reply)

    async def barge_in(self) -> None:
        """Signal that the user has started speaking — stop Gemini output."""
        logger.debug("Barge-in received (mock)")

    async def close(self) -> None:
        self._active = False
        logger.info("MockLiveSession closed")


# ---------------------------------------------------------------------------
# Real Gemini Live session
# ---------------------------------------------------------------------------

class GeminiLiveSession:
    """Wraps the Gemini Live API for bidirectional audio streaming."""

    MODEL = "gemini-2.5-flash-native-audio-latest"

    def __init__(
        self,
        api_key: str,
        on_audio: AudioChunkCallback,
        on_text: Callable[[str], None],
        on_input_transcript: Optional[Callable[[str], None]] = None,
        on_session_end: Optional[Callable[[str], None]] = None,
    ):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._on_audio = on_audio
        self._on_text = on_text
        self._on_input_transcript = on_input_transcript
        self._on_session_end = on_session_end
        self._session = None
        self._receive_task: Optional[asyncio.Task] = None
        self._active = False

    async def start(self, system_prompt: str, first_question: str = "") -> None:
        """Open a Live API session with the given system prompt."""
        from google.genai import types

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt)]
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

        logger.info("Connecting to Gemini Live API (%s)...", self.MODEL)
        async with self._client.aio.live.connect(
            model=self.MODEL, config=config
        ) as session:
            self._session = session
            self._active = True
            logger.info("Gemini Live session connected")

            # Gemini Live won't speak first — send a brief trigger to start
            # The system prompt already contains full interview context
            await session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text="Hi, I'm ready to begin the interview.")],
                ),
                turn_complete=True,
            )
            logger.info("Sent initial trigger to Gemini")

            await self._receive_loop()

    async def send_audio(self, chunk: bytes) -> None:
        """Forward PCM audio chunk to Gemini."""
        if not self._session or not self._active:
            return
        try:
            from google.genai import types
            await self._session.send_realtime_input(
                media=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"),
            )
        except Exception as exc:
            logger.warning("Error sending audio: %s", exc)

    async def send_text(self, text: str) -> None:
        """Send text message into the live session."""
        if not self._session or not self._active:
            return
        try:
            from google.genai import types
            await self._session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=text)],
                ),
                turn_complete=True,
            )
        except Exception as exc:
            logger.warning("Error sending text: %s", exc)

    async def barge_in(self) -> None:
        """Signal barge-in (Gemini handles this via VAD automatically)."""
        logger.debug("Barge-in signal received")

    async def close(self) -> None:
        self._active = False
        if self._receive_task:
            self._receive_task.cancel()
        logger.info("GeminiLiveSession closed")

    async def _receive_loop(self) -> None:
        """Read audio/text responses from Gemini and dispatch via callbacks.

        The receive() async generator may complete after each model turn.
        We call it in a loop to support multi-turn conversation.
        """
        end_reason = "unknown"
        turn_count = 0
        try:
            while self._active:
                had_messages = False
                turn_text_buffer = ""  # Accumulate output transcription per turn
                try:
                    async for response in self._session.receive():
                        had_messages = True
                        if not self._active:
                            end_reason = "session closed by server"
                            return

                        server_content = getattr(response, "server_content", None)
                        if not server_content:
                            logger.debug("Non-content response: %s", type(response).__name__)
                            continue

                        # Check for interruption
                        if getattr(server_content, "interrupted", False):
                            logger.debug("Gemini interrupted by user speech")
                            # Send whatever text was accumulated before interruption
                            if turn_text_buffer.strip():
                                self._on_text(turn_text_buffer.strip())
                                turn_text_buffer = ""
                            continue

                        model_turn = getattr(server_content, "model_turn", None)
                        if model_turn and model_turn.parts:
                            for part in model_turn.parts:
                                inline_data = getattr(part, "inline_data", None)
                                if inline_data and isinstance(inline_data.data, bytes):
                                    await self._on_audio(inline_data.data)

                        # Check for input transcription (user's speech-to-text)
                        input_transcription = getattr(server_content, "input_transcription", None)
                        if input_transcription and input_transcription.text:
                            logger.info("User said: %s", input_transcription.text)
                            if self._on_input_transcript:
                                self._on_input_transcript(input_transcription.text)

                        # Accumulate output transcription — send as one message at turn end
                        output_transcription = getattr(server_content, "output_transcription", None)
                        if output_transcription and output_transcription.text:
                            turn_text_buffer += output_transcription.text

                        # Check for turn completion
                        turn_complete = getattr(server_content, "turn_complete", False)
                        if turn_complete:
                            turn_count += 1
                            logger.info("Gemini turn %d complete", turn_count)
                            # Send accumulated transcription as a single message
                            if turn_text_buffer.strip():
                                self._on_text(turn_text_buffer.strip())
                                # Detect interview wrap-up phrase
                                if "best of luck" in turn_text_buffer.lower():
                                    logger.info("Interview wrap-up detected at turn %d", turn_count)
                                    end_reason = f"Interview completed after {turn_count} turn(s)"
                                    self._active = False
                                    turn_text_buffer = ""
                                    break
                                turn_text_buffer = ""
                            break  # exit inner loop, re-enter receive()

                except StopAsyncIteration:
                    pass  # receive() generator exhausted for this turn, loop to next
                # Flush any remaining text
                if turn_text_buffer.strip():
                    self._on_text(turn_text_buffer.strip())
                    turn_text_buffer = ""

                if not had_messages:
                    # receive() returned immediately with no messages — connection dead
                    end_reason = f"Gemini connection lost after {turn_count} turn(s)"
                    break

                # Generator exhausted but session active — re-enter receive() for next turn
                logger.info("Re-entering receive() loop after turn %d", turn_count)

        except asyncio.CancelledError:
            logger.info("Receive loop cancelled")
            return
        except Exception as exc:
            end_reason = str(exc)
            logger.error("Receive loop error: %s", exc, exc_info=True)

        if end_reason == "unknown":
            end_reason = f"Session ended after {turn_count} turn(s)"

        logger.warning("Gemini Live session ended: %s", end_reason)
        self._active = False
        if self._on_session_end:
            self._on_session_end(end_reason)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_live_session(
    on_audio: AudioChunkCallback,
    on_text: Callable[[str], None],
    on_input_transcript: Optional[Callable[[str], None]] = None,
    on_session_end: Optional[Callable[[str], None]] = None,
    api_key: Optional[str] = None,
) -> MockLiveSession | GeminiLiveSession:
    """Return a real or mock session depending on API key availability."""
    key = api_key or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        return MockLiveSession(on_audio=on_audio, on_text=on_text, on_input_transcript=on_input_transcript, on_session_end=on_session_end)
    return GeminiLiveSession(api_key=key, on_audio=on_audio, on_text=on_text, on_input_transcript=on_input_transcript, on_session_end=on_session_end)
