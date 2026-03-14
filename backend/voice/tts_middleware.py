"""Gemini TTS middleware for COUNCIL voice interactions.

Uses Google Gemini 2.5 Flash TTS via REST API (no SDK dependency).
Outputs WAV audio (24kHz, 16-bit, mono PCM).
"""

import os
import struct
import base64
import asyncio
import logging
from typing import AsyncGenerator
from dotenv import load_dotenv

import httpx

logger = logging.getLogger(__name__)

load_dotenv()

# WAV header constants
SAMPLE_RATE = 24000
CHANNELS = 1
BITS_PER_SAMPLE = 16
BYTES_PER_SAMPLE = BITS_PER_SAMPLE // 8

TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def inject_emotion_tags(text: str, emotional_state) -> str:
    """Prepend Gemini-compatible style instructions based on emotional state."""
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


async def _call_gemini_tts(api_key: str, text: str, voice_name: str) -> bytes | None:
    """Call Gemini TTS REST API and return raw PCM audio bytes."""
    url = f"{GEMINI_API_URL}/{TTS_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name}
                }
            },
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.error("Gemini TTS API error: %s %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts and "inlineData" in parts[0]:
                audio_b64 = parts[0]["inlineData"]["data"]
                return base64.b64decode(audio_b64)

    return None


class VoiceMiddleware:
    """Handles text-to-speech using Google Gemini TTS REST API."""

    def __init__(self):
        self._api_key = os.environ.get("GEMINI_API_KEY")
        self._character_voices: dict[str, str] = {}
        if self._api_key:
            logger.info("Gemini TTS configured (REST API, no SDK)")
        else:
            logger.warning("GEMINI_API_KEY not set — voice disabled")

    def set_character_voices(self, voice_map: dict[str, str]):
        """Set dynamic character->voice mapping."""
        self._character_voices.update(voice_map)

    @property
    def available(self) -> bool:
        return self._api_key is not None

    async def text_to_speech(self, text: str, agent_id: str) -> bytes | None:
        """Convert text to speech audio. Returns WAV bytes or None."""
        if not self.available:
            return None

        voice_name = self._character_voices.get(agent_id, "Kore")

        try:
            logger.info("TTS request: agent=%s, voice=%s, text_len=%d",
                        agent_id, voice_name, len(text))

            pcm_data = await _call_gemini_tts(self._api_key, text, voice_name)
            if pcm_data:
                wav_data = _pcm_to_wav(pcm_data)
                logger.info("TTS success: %d bytes", len(wav_data))
                return wav_data

            logger.warning("TTS returned no audio data")
            return None
        except Exception as e:
            logger.error("TTS generation failed: %s: %s", type(e).__name__, e)
            return None

    async def stream_tts(self, text: str, voice_id: str) -> AsyncGenerator[bytes, None]:
        """Generate TTS audio and yield as a single WAV chunk."""
        if not self.available:
            return

        try:
            pcm_data = await _call_gemini_tts(self._api_key, text, voice_id)
            if pcm_data:
                yield _pcm_to_wav(pcm_data)
            else:
                logger.warning("TTS stream returned no audio data")
        except Exception as e:
            logger.error("TTS stream failed: %s: %s", type(e).__name__, e)
            return
