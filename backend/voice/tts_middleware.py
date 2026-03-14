"""Gemini TTS middleware for COUNCIL voice interactions.

Uses Google Gemini 2.5 Flash TTS for high-quality text-to-speech.
Outputs WAV audio (24kHz, 16-bit, mono PCM).
"""

import os
import struct
import asyncio
import logging
from typing import AsyncGenerator
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# WAV header constants
SAMPLE_RATE = 24000
CHANNELS = 1
BITS_PER_SAMPLE = 16
BYTES_PER_SAMPLE = BITS_PER_SAMPLE // 8

TTS_MODEL = "gemini-2.5-flash-preview-tts"


def inject_emotion_tags(text: str, emotional_state) -> str:
    """Prepend Gemini-compatible style instructions based on emotional state.

    Gemini TTS uses natural language style cues in the content itself.
    """
    if emotional_state.anger > 0.6:
        return f"Say this angrily and intensely: {text}"
    if emotional_state.fear > 0.6:
        return f"Say this fearfully, with a trembling voice: {text}"
    if emotional_state.happiness > 0.7 and emotional_state.energy > 0.6:
        return f"Say this with excitement and energy: {text}"
    if emotional_state.happiness > 0.7:
        return f"Say this cheerfully: {text}"
    if emotional_state.curiosity > 0.7:
        return f"Say this with curiosity, as if pondering something: {text}"
    if emotional_state.trust < 0.3:
        return f"Say this suspiciously, with doubt in your voice: {text}"
    if emotional_state.energy < 0.2:
        return f"Say this wearily, as if exhausted: {text}"
    return text


def _pcm_to_wav(pcm_data: bytes) -> bytes:
    """Convert raw PCM bytes to WAV format (24kHz, 16-bit, mono)."""
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,  # Subchunk1Size
        1,   # PCM format
        CHANNELS,
        SAMPLE_RATE,
        SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE,  # ByteRate
        CHANNELS * BYTES_PER_SAMPLE,  # BlockAlign
        BITS_PER_SAMPLE,
        b"data",
        data_size,
    )
    return header + pcm_data


class VoiceMiddleware:
    """Handles text-to-speech using Google Gemini TTS."""

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        self.client = None
        if api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=api_key)
                logger.info("Gemini TTS client initialized")
            except ImportError:
                logger.warning("google-genai package not installed")
        else:
            logger.warning("GEMINI_API_KEY not set — voice disabled")
        self._character_voices: dict[str, str] = {}

    def set_character_voices(self, voice_map: dict[str, str]):
        """Set dynamic character->voice mapping.

        Args:
            voice_map: dict mapping character_id to Gemini voice name
                       (e.g. {"abc123": "Kore"})
        """
        self._character_voices.update(voice_map)

    @property
    def available(self) -> bool:
        return self.client is not None

    async def text_to_speech(self, text: str, agent_id: str) -> bytes | None:
        """Convert text to speech audio.

        Returns WAV audio bytes or None if TTS is unavailable.
        """
        if not self.available:
            return None

        voice_name = self._character_voices.get(agent_id, "Kore")

        try:
            from google.genai import types

            logger.info("TTS request: agent=%s, voice=%s, text_len=%d",
                        agent_id, voice_name, len(text))

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=TTS_MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name,
                            )
                        )
                    ),
                ),
            )

            if (response.candidates
                    and response.candidates[0].content.parts
                    and response.candidates[0].content.parts[0].inline_data):
                pcm_data = response.candidates[0].content.parts[0].inline_data.data
                wav_data = _pcm_to_wav(pcm_data)
                logger.info("TTS success: %d bytes (PCM %d bytes)", len(wav_data), len(pcm_data))
                return wav_data

            logger.warning("TTS returned no audio data")
            return None
        except Exception as e:
            logger.error("TTS generation failed: %s: %s", type(e).__name__, e)
            return None

    async def stream_tts(self, text: str, voice_id: str) -> AsyncGenerator[bytes, None]:
        """Generate TTS audio and yield as a single WAV chunk.

        Gemini TTS does not support true streaming, so we generate the full
        audio and yield it as one chunk with a WAV header. The frontend
        Audio element handles progressive playback.

        Args:
            text: Text to convert to speech.
            voice_id: Gemini voice name (e.g. "Kore", "Puck").

        Yields:
            WAV audio bytes.
        """
        if not self.available:
            return

        try:
            from google.genai import types

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=TTS_MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_id,
                            )
                        )
                    ),
                ),
            )

            if (response.candidates
                    and response.candidates[0].content.parts
                    and response.candidates[0].content.parts[0].inline_data):
                pcm_data = response.candidates[0].content.parts[0].inline_data.data
                yield _pcm_to_wav(pcm_data)
            else:
                logger.warning("TTS stream returned no audio data")
        except Exception as e:
            logger.error("TTS stream failed: %s: %s", type(e).__name__, e)
            return
