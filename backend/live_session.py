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

    def __init__(self, on_audio: AudioChunkCallback, on_text: Callable[[str], None]):
        self._on_audio = on_audio
        self._on_text = on_text
        self._active = False
        self._task: Optional[asyncio.Task] = None
        self._turn_count = 0

    async def start(self, system_prompt: str) -> None:
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
    """Wraps the Gemini Live API (gemini-2.5-flash-native-audio-preview).

    TODO: Implement once the google-genai SDK exposes Live API bindings.
    See: https://ai.google.dev/gemini-api/docs/live
    """

    MODEL = "gemini-2.5-flash-native-audio-preview"

    def __init__(
        self,
        api_key: str,
        on_audio: AudioChunkCallback,
        on_text: Callable[[str], None],
    ):
        self._api_key = api_key
        self._on_audio = on_audio
        self._on_text = on_text
        self._session = None
        self._receive_task: Optional[asyncio.Task] = None

    async def start(self, system_prompt: str) -> None:
        """Open a Live API session with the given system prompt."""
        # TODO: wire up real SDK
        # from google import genai
        # from google.genai import types
        #
        # client = genai.Client(api_key=self._api_key)
        # config = types.LiveConnectConfig(
        #     response_modalities=["AUDIO"],
        #     system_instruction=system_prompt,
        #     speech_config=types.SpeechConfig(
        #         voice_config=types.VoiceConfig(
        #             prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
        #         )
        #     ),
        # )
        # async with client.aio.live.connect(model=self.MODEL, config=config) as session:
        #     self._session = session
        #     self._receive_task = asyncio.create_task(self._receive_loop())
        #     await self._receive_task
        raise NotImplementedError("Real Gemini Live session not yet wired up")

    async def send_audio(self, chunk: bytes) -> None:
        """Forward PCM audio chunk to Gemini."""
        # TODO:
        # await self._session.send(
        #     types.LiveClientRealtimeInput(
        #         media_chunks=[types.Blob(data=chunk, mime_type="audio/pcm")]
        #     )
        # )
        pass

    async def barge_in(self) -> None:
        """Interrupt current Gemini turn."""
        # TODO: await self._session.send(types.LiveClientRealtimeInput(end_of_turn=True))
        pass

    async def close(self) -> None:
        if self._receive_task:
            self._receive_task.cancel()

    async def _receive_loop(self) -> None:
        """Read audio/text responses from Gemini and dispatch via callbacks."""
        # TODO:
        # async for response in self._session.receive():
        #     for part in response.server_content.model_turn.parts:
        #         if part.inline_data:
        #             self._on_audio(part.inline_data.data)
        #         elif part.text:
        #             self._on_text(part.text)
        pass


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_live_session(
    on_audio: AudioChunkCallback,
    on_text: Callable[[str], None],
    api_key: Optional[str] = None,
) -> MockLiveSession | GeminiLiveSession:
    """Return a real or mock session depending on API key availability."""
    key = api_key or os.getenv("GOOGLE_API_KEY", "")
    if not key:
        return MockLiveSession(on_audio=on_audio, on_text=on_text)
    return GeminiLiveSession(api_key=key, on_audio=on_audio, on_text=on_text)
