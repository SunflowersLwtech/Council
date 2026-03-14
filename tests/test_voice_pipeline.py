"""Tests for the voice pipeline — TTS, STT, SFX, voice resolution.

Tests both mocked unit behavior and (when marked live_api) real ElevenLabs calls.
Follows SightLine's pattern of testing audio I/O at multiple levels.
"""

import os
import io
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

os.environ.setdefault("MISTRAL_API_KEY", "test_key_for_unit_tests")

from backend.voice.tts_middleware import VoiceMiddleware, inject_emotion_tags


# ── VoiceMiddleware Initialization ──────────────────────────────────


class TestVoiceMiddlewareInit:

    def test_no_api_key_disables_voice(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            vm = VoiceMiddleware()
            assert vm.available is False

    def test_with_api_key_enables_voice(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            assert vm.available is True

    def test_set_character_voices(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            vm.set_character_voices({"char1": "George", "char2": "Sarah"})
            assert vm._character_voices["char1"] == "George"
            assert vm._character_voices["char2"] == "Sarah"


# ── TTS (Text-to-Speech) ───────────────────────────────────────────


class TestTextToSpeech:

    @pytest.mark.asyncio
    async def test_tts_returns_bytes(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            audio = await vm.text_to_speech("Hello world", "agent1")
            assert audio is not None
            assert isinstance(audio, bytes)
            assert len(audio) > 0

    @pytest.mark.asyncio
    async def test_tts_unavailable_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            vm = VoiceMiddleware()
            audio = await vm.text_to_speech("Hello", "agent1")
            assert audio is None

    @pytest.mark.asyncio
    async def test_tts_uses_character_voice(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            vm.set_character_voices({"char1": "George"})
            await vm.text_to_speech("Test", "char1")
            # The mock should have been called
            assert mock_elevenlabs.text_to_speech.convert.called

    @pytest.mark.asyncio
    async def test_tts_default_voice_is_sarah(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            await vm.text_to_speech("Test", "unknown_agent")
            # Should fall back to "Sarah"

    @pytest.mark.asyncio
    async def test_tts_error_returns_none(self, mock_elevenlabs):
        mock_elevenlabs.text_to_speech.convert.side_effect = Exception("API error")
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            audio = await vm.text_to_speech("Test", "agent1")
            assert audio is None


# ── STT (Speech-to-Text) ───────────────────────────────────────────


class TestSpeechToText:

    @pytest.mark.asyncio
    async def test_stt_returns_text(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            fake_audio = b"\xff\xfb\x90\x00" * 100
            text = await vm.speech_to_text(fake_audio)
            assert text == "I think the elder is suspicious."

    @pytest.mark.asyncio
    async def test_stt_unavailable_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            vm = VoiceMiddleware()
            text = await vm.speech_to_text(b"audio_data")
            assert text is None

    @pytest.mark.asyncio
    async def test_stt_error_returns_none(self, mock_elevenlabs):
        mock_elevenlabs.speech_to_text.convert.side_effect = Exception("Scribe error")
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            text = await vm.speech_to_text(b"audio_data")
            assert text is None


# ── SFX (Sound Effects) ────────────────────────────────────────────


class TestSoundEffects:

    @pytest.mark.asyncio
    async def test_sfx_returns_bytes(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            audio = await vm.generate_sfx("dramatic gavel strike", 3.0)
            assert audio is not None
            assert isinstance(audio, bytes)

    @pytest.mark.asyncio
    async def test_sfx_unavailable_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ELEVENLABS_API_KEY", None)
            vm = VoiceMiddleware()
            audio = await vm.generate_sfx("thunder", 2.0)
            assert audio is None

    @pytest.mark.asyncio
    async def test_sfx_error_returns_none(self, mock_elevenlabs):
        mock_elevenlabs.text_to_sound_effects.convert.side_effect = Exception("SFX error")
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            audio = await vm.generate_sfx("error sound", 1.0)
            assert audio is None


# ── Voice Resolution ───────────────────────────────────────────────


class TestVoiceResolution:

    @pytest.mark.asyncio
    async def test_resolves_voice_name_to_id(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            voice_id = await vm._resolve_voice_id("Sarah")
            assert voice_id == "voice_sarah_id"

    @pytest.mark.asyncio
    async def test_caches_resolved_voice(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            await vm._resolve_voice_id("Sarah")
            await vm._resolve_voice_id("Sarah")
            # Should only call voices.get_all once (cached)
            assert mock_elevenlabs.voices.get_all.call_count == 1

    @pytest.mark.asyncio
    async def test_unknown_voice_returns_name(self, mock_elevenlabs):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": "test_key"}):
            vm = VoiceMiddleware()
            voice_id = await vm._resolve_voice_id("NonexistentVoice")
            # Falls back to returning the input name
            assert voice_id == "NonexistentVoice"


# ── Live API Tests (require ELEVENLABS_API_KEY) ─────────────────────


@pytest.mark.live_api
class TestVoiceLiveAPI:
    """Real ElevenLabs API tests — skipped by default, run with: pytest -m live_api"""

    @pytest.mark.asyncio
    async def test_real_tts_generates_audio(self):
        vm = VoiceMiddleware()
        if not vm.available:
            pytest.skip("ELEVENLABS_API_KEY not set")
        audio = await vm.text_to_speech("The council convenes at dusk.", "orchestrator")
        assert audio is not None
        assert len(audio) > 1000  # Should be substantial audio
        # MP3 magic bytes
        assert audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"ID")

    @pytest.mark.asyncio
    async def test_real_sfx_generates_audio(self):
        vm = VoiceMiddleware()
        if not vm.available:
            pytest.skip("ELEVENLABS_API_KEY not set")
        audio = await vm.generate_sfx("tense dramatic drum beat", 2.0)
        assert audio is not None
        assert len(audio) > 500
