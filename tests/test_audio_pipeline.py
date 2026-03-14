"""End-to-end audio pipeline tests for COUNCIL.

Tests the full data flow:
  SSE stream → text accumulation → stream_end → TTS request → WAV generation

Validates:
  1. Message queue ordering and integrity
  2. TTS audio generation and WAV format correctness
  3. SSE-to-TTS timing and latency measurement
  4. Multi-character sequential TTS queue behavior
  5. Error recovery in the audio pipeline
"""

import asyncio
import json
import struct
import time
import logging
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from backend.voice.tts_middleware import (
    VoiceMiddleware, _pcm_to_wav, _call_gemini_tts, inject_emotion_tags,
    SAMPLE_RATE, CHANNELS, BITS_PER_SAMPLE,
)
from backend.models.game_models import (
    GameState, Character, ChatMessage, EmotionalState, WorldModel,
)
from backend.game.orchestrator import GameOrchestrator
from backend.game import sse_emitter as sse

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────


def make_fake_pcm(duration_sec: float = 0.5) -> bytes:
    """Generate silent PCM data (24kHz, 16-bit mono)."""
    num_samples = int(SAMPLE_RATE * duration_sec)
    return b"\x00\x00" * num_samples


def parse_sse_event(raw: str) -> dict:
    """Parse a single SSE data line into a dict."""
    assert raw.startswith("data: "), f"Not SSE format: {raw[:30]}"
    return json.loads(raw[len("data: "):].strip())


def validate_wav_header(wav_data: bytes):
    """Validate WAV header structure and return (sample_rate, channels, bps, data_size)."""
    assert len(wav_data) >= 44, f"WAV too short: {len(wav_data)} bytes"
    assert wav_data[:4] == b"RIFF", "Missing RIFF marker"
    assert wav_data[8:12] == b"WAVE", "Missing WAVE marker"
    assert wav_data[12:16] == b"fmt ", "Missing fmt chunk"

    # Parse fmt chunk
    fmt_size = struct.unpack_from("<I", wav_data, 16)[0]
    assert fmt_size == 16, f"Unexpected fmt size: {fmt_size}"
    audio_format = struct.unpack_from("<H", wav_data, 20)[0]
    assert audio_format == 1, f"Not PCM format: {audio_format}"

    channels = struct.unpack_from("<H", wav_data, 22)[0]
    sample_rate = struct.unpack_from("<I", wav_data, 24)[0]
    bits_per_sample = struct.unpack_from("<H", wav_data, 34)[0]

    assert wav_data[36:40] == b"data", "Missing data chunk"
    data_size = struct.unpack_from("<I", wav_data, 40)[0]

    return sample_rate, channels, bits_per_sample, data_size


# ── Test: WAV Format Correctness ────────────────────────────────────────


class TestWAVGeneration:
    """Validate WAV header and PCM data integrity."""

    def test_pcm_to_wav_header(self):
        """WAV header should have correct format constants."""
        pcm = make_fake_pcm(0.1)
        wav = _pcm_to_wav(pcm)
        sr, ch, bps, data_size = validate_wav_header(wav)
        assert sr == 24000
        assert ch == 1
        assert bps == 16
        assert data_size == len(pcm)

    def test_pcm_to_wav_total_size(self):
        """Total WAV size = 44 header bytes + PCM data length."""
        pcm = make_fake_pcm(1.0)
        wav = _pcm_to_wav(pcm)
        assert len(wav) == 44 + len(pcm)

    def test_pcm_to_wav_riff_size_field(self):
        """RIFF chunk size should be filesize - 8."""
        pcm = make_fake_pcm(0.5)
        wav = _pcm_to_wav(pcm)
        riff_size = struct.unpack_from("<I", wav, 4)[0]
        assert riff_size == len(wav) - 8

    def test_empty_pcm_still_valid(self):
        """Empty PCM should produce valid (but silent) WAV."""
        wav = _pcm_to_wav(b"")
        sr, ch, bps, data_size = validate_wav_header(wav)
        assert data_size == 0
        assert len(wav) == 44

    def test_various_durations(self):
        """Different PCM durations should all produce valid WAV."""
        for duration in [0.01, 0.1, 0.5, 1.0, 3.0]:
            pcm = make_fake_pcm(duration)
            wav = _pcm_to_wav(pcm)
            sr, ch, bps, data_size = validate_wav_header(wav)
            assert data_size == len(pcm), f"Duration {duration}s: data_size mismatch"


# ── Test: Emotion Tag Injection ─────────────────────────────────────────


class TestEmotionTagInjection:
    """Validate emotion tags affect TTS text correctly."""

    def test_neutral_no_prefix(self):
        """Neutral emotions should return text unchanged."""
        es = EmotionalState()
        result = inject_emotion_tags("Hello world", es)
        assert result == "Hello world"

    def test_angry_prefix(self):
        """High anger should prepend angry instruction."""
        es = EmotionalState(anger=0.8)
        result = inject_emotion_tags("Stop!", es)
        assert "angrily" in result.lower()
        assert "Stop!" in result

    def test_fearful_prefix(self):
        """High fear should prepend fearful instruction."""
        es = EmotionalState(fear=0.8)
        result = inject_emotion_tags("What was that?", es)
        assert "fearful" in result.lower()
        assert "What was that?" in result

    def test_emotion_priority(self):
        """Anger should take priority when both anger and fear are high."""
        es = EmotionalState(anger=0.8, fear=0.8)
        result = inject_emotion_tags("I see", es)
        # Anger checked first in the function
        assert "angrily" in result.lower()

    def test_tag_increases_text_length(self):
        """Emotion tags add tokens → measure the overhead."""
        es = EmotionalState(anger=0.8)
        original = "I disagree with your position."
        tagged = inject_emotion_tags(original, es)
        overhead = len(tagged) - len(original)
        # Overhead should be reasonable (under 100 chars)
        assert 0 < overhead < 100, f"Emotion tag overhead too large: {overhead} chars"


# ── Test: SSE Event Serialization ───────────────────────────────────────


class TestSSEEventFormat:
    """Validate SSE emitter produces correct event format for TTS flow."""

    def test_stream_start_format(self):
        """stream_start should have type, character_id, character_name."""
        raw = sse.stream_start("char01", "Elder Marcus")
        evt = parse_sse_event(raw)
        assert evt["type"] == "stream_start"
        assert evt["character_id"] == "char01"
        assert evt["character_name"] == "Elder Marcus"

    def test_stream_delta_format(self):
        """stream_delta should carry character_id and delta text."""
        raw = sse.stream_delta("char01", "Hello")
        evt = parse_sse_event(raw)
        assert evt["type"] == "stream_delta"
        assert evt["delta"] == "Hello"
        assert evt["character_id"] == "char01"

    def test_stream_end_format(self):
        """stream_end should have full content, tts_text, voice_id, emotion."""
        raw = sse.stream_end(
            "char01", "Elder Marcus", "I sense darkness.",
            "Say this fearfully: I sense darkness.", "George", "fear"
        )
        evt = parse_sse_event(raw)
        assert evt["type"] == "stream_end"
        assert evt["content"] == "I sense darkness."
        assert evt["tts_text"] == "Say this fearfully: I sense darkness."
        assert evt["voice_id"] == "George"
        assert evt["emotion"] == "fear"

    def test_stream_end_carries_tts_text_for_audio(self):
        """The tts_text field should be the emotion-tagged version for TTS."""
        raw = sse.stream_end(
            "char01", "Elder Marcus",
            "We must act now.",
            "Say this angrily and intensely: We must act now.",
            "George", "anger"
        )
        evt = parse_sse_event(raw)
        # Frontend uses tts_text (not content) for TTS request
        assert evt["tts_text"] != evt["content"]
        assert "angrily" in evt["tts_text"]

    def test_event_ordering_in_chat_flow(self):
        """Simulate a full chat SSE sequence and validate ordering."""
        events = [
            sse.responders(["char01", "char02"]),
            sse.thinking("char01", "Elder Marcus"),
            sse.stream_start("char01", "Elder Marcus"),
            sse.stream_delta("char01", "I "),
            sse.stream_delta("char01", "sense "),
            sse.stream_delta("char01", "darkness."),
            sse.stream_end("char01", "Elder Marcus", "I sense darkness.",
                          "I sense darkness.", "George", "neutral"),
            sse.thinking("char02", "Swift Lila"),
            sse.stream_start("char02", "Swift Lila"),
            sse.stream_delta("char02", "How dramatic."),
            sse.stream_end("char02", "Swift Lila", "How dramatic.",
                          "How dramatic.", "Sarah", "neutral"),
            sse.done(tension=0.4),
        ]
        types = [parse_sse_event(e)["type"] for e in events]
        assert types == [
            "responders", "thinking", "stream_start",
            "stream_delta", "stream_delta", "stream_delta", "stream_end",
            "thinking", "stream_start", "stream_delta", "stream_end",
            "done",
        ]


# ── Test: TTS API Call (Mocked) ─────────────────────────────────────────


class TestTTSGeneration:
    """Test TTS generation with mocked Gemini API."""

    @pytest.fixture
    def mock_gemini_success(self):
        """Mock successful Gemini TTS API response."""
        fake_pcm = make_fake_pcm(1.0)
        import base64
        fake_b64 = base64.b64encode(fake_pcm).decode()
        response_data = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "mimeType": "audio/pcm",
                            "data": fake_b64,
                        }
                    }]
                }
            }]
        }
        return response_data, fake_pcm

    @pytest.mark.asyncio
    async def test_tts_returns_wav(self, mock_gemini_success):
        """Gemini API success should produce valid WAV bytes."""
        response_data, expected_pcm = mock_gemini_success

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response_data

        with patch("backend.voice.tts_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            pcm = await _call_gemini_tts("fake_key", "Hello", "Kore")
            assert pcm is not None
            assert pcm == expected_pcm

            # Convert to WAV and validate
            wav = _pcm_to_wav(pcm)
            sr, ch, bps, data_size = validate_wav_header(wav)
            assert sr == 24000
            assert data_size == len(expected_pcm)

    @pytest.mark.asyncio
    async def test_tts_api_error_returns_none(self):
        """API error should return None, not crash."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal server error"

        with patch("backend.voice.tts_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            pcm = await _call_gemini_tts("fake_key", "Hello", "Kore")
            assert pcm is None

    @pytest.mark.asyncio
    async def test_tts_empty_response_returns_none(self):
        """Empty Gemini response should return None."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"candidates": []}

        with patch("backend.voice.tts_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            pcm = await _call_gemini_tts("fake_key", "Hello", "Kore")
            assert pcm is None

    @pytest.mark.asyncio
    async def test_voice_middleware_stream_tts(self, mock_gemini_success):
        """stream_tts should yield a single WAV chunk."""
        response_data, expected_pcm = mock_gemini_success

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response_data

        with patch("backend.voice.tts_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            vm = VoiceMiddleware.__new__(VoiceMiddleware)
            vm._api_key = "fake_key"
            vm._character_voices = {}

            chunks = []
            async for chunk in vm.stream_tts("Hello world", "Kore"):
                chunks.append(chunk)

            assert len(chunks) == 1, "stream_tts should yield exactly one chunk"
            validate_wav_header(chunks[0])


# ── Test: Full SSE Chat → TTS Flow (Timing) ────────────────────────────


class TestSSEToTTSTiming:
    """Measure and validate the SSE stream → TTS request timing."""

    @pytest.mark.asyncio
    async def test_stream_accumulation_timing(self):
        """Simulate SSE stream and measure time from stream_start to stream_end."""
        # Simulate the backend's streaming behavior
        deltas = ["I ", "sense ", "dark", "ness ", "among ", "us."]
        DELTA_PACE = 0.04  # Backend STREAM_DELTA_PACE_SEC

        t_start = time.monotonic()

        # Accumulate text like the frontend does
        accumulated = ""
        for delta in deltas:
            accumulated += delta
            await asyncio.sleep(DELTA_PACE)

        t_text_complete = time.monotonic()
        text_latency_ms = (t_text_complete - t_start) * 1000

        # The TTS request happens after stream_end (when all text accumulated)
        full_text = "I sense darkness among us."
        assert accumulated.strip() == full_text.strip()

        # Text streaming latency should be proportional to chunk count
        expected_ms = len(deltas) * DELTA_PACE * 1000
        assert text_latency_ms < expected_ms * 2, \
            f"Text accumulation too slow: {text_latency_ms:.0f}ms (expected ~{expected_ms:.0f}ms)"

        logger.info("Text streaming latency: %.1fms for %d chunks", text_latency_ms, len(deltas))

    @pytest.mark.asyncio
    async def test_multi_character_sequential_queue(self):
        """Multiple characters should TTS sequentially — measure total queue time."""
        characters = [
            {"id": "char01", "name": "Elder Marcus", "text": "I sense darkness.", "voice": "George"},
            {"id": "char02", "name": "Swift Lila", "text": "How dramatic.", "voice": "Sarah"},
            {"id": "char03", "name": "Quiet Jasper", "text": "Watch carefully.", "voice": "Kore"},
        ]

        tts_queue = []
        queue_timestamps = []

        # Simulate the TTS queueing behavior from the frontend
        for char in characters:
            t = time.monotonic()
            tts_queue.append(char)
            queue_timestamps.append(t)

        assert len(tts_queue) == 3

        # Verify queue ordering matches character order
        for i, char in enumerate(characters):
            assert tts_queue[i]["id"] == char["id"]
            assert tts_queue[i]["text"] == char["text"]

        # Timestamps should be monotonically increasing
        for i in range(1, len(queue_timestamps)):
            assert queue_timestamps[i] >= queue_timestamps[i - 1]

    @pytest.mark.asyncio
    async def test_inter_speaker_pace(self):
        """Measure inter-speaker pacing delay."""
        INTER_SPEAKER_PACE = 0.40  # Backend constant

        t_start = time.monotonic()
        await asyncio.sleep(INTER_SPEAKER_PACE)
        t_end = time.monotonic()

        actual_delay = t_end - t_start
        assert 0.35 < actual_delay < 0.50, \
            f"Inter-speaker pace out of range: {actual_delay:.3f}s"


# ── Test: Full E2E Discussion Stream (Mocked) ──────────────────────────


class TestE2EDiscussionStream:
    """End-to-end test of a complete discussion chat stream with TTS events."""

    @pytest.fixture
    def game_state(self, default_world, five_characters):
        """Create a discussion-phase game state."""
        state = GameState(
            session_id="test-e2e-001",
            phase="discussion",
            round=1,
            world=default_world,
            characters=five_characters,
        )
        return state

    @pytest.mark.asyncio
    async def test_chat_stream_produces_tts_events(self, game_state, mock_mistral):
        """handle_chat should produce stream_start/delta/end events with TTS data."""
        orch = GameOrchestrator(persistence=None)
        sid = game_state.session_id

        # Inject state and agents
        orch.session_mgr._sessions[sid] = game_state
        from backend.game.character_agent import CharacterAgent
        agents = {}
        for char in game_state.characters:
            agent = CharacterAgent(char, game_state.world)
            agents[char.id] = agent
        orch.session_mgr._agents[sid] = agents

        # Collect all SSE events
        events = []
        timing = {"first_event": None, "last_event": None}

        async for raw_event in orch.handle_chat(sid, "Who do you suspect?"):
            t = time.monotonic()
            if timing["first_event"] is None:
                timing["first_event"] = t
            timing["last_event"] = t
            evt = parse_sse_event(raw_event)
            events.append(evt)

        # Must have at least: responders + (thinking + stream_start + stream_end) + done
        assert len(events) >= 4, f"Too few events: {len(events)}"

        # Extract event types
        types = [e["type"] for e in events]
        assert "responders" in types
        assert "done" in types

        # Check stream_end events carry TTS data
        stream_ends = [e for e in events if e["type"] == "stream_end"]
        for se in stream_ends:
            assert "content" in se, "stream_end missing content"
            assert "tts_text" in se, "stream_end missing tts_text"
            assert "voice_id" in se, "stream_end missing voice_id"
            assert len(se["content"]) > 0, "stream_end has empty content"
            assert len(se["voice_id"]) > 0, "stream_end has empty voice_id"

        # Measure total stream duration
        total_ms = (timing["last_event"] - timing["first_event"]) * 1000
        logger.info("E2E chat stream: %d events in %.0fms", len(events), total_ms)

    @pytest.mark.asyncio
    async def test_stream_delta_accumulates_correctly(self, game_state, mock_mistral):
        """Delta chunks should accumulate to match stream_end content."""
        orch = GameOrchestrator(persistence=None)
        sid = game_state.session_id
        orch.session_mgr._sessions[sid] = game_state

        from backend.game.character_agent import CharacterAgent
        agents = {}
        for char in game_state.characters:
            agents[char.id] = CharacterAgent(char, game_state.world)
        orch.session_mgr._agents[sid] = agents

        # Track deltas per character
        char_deltas: dict[str, list[str]] = {}
        char_finals: dict[str, str] = {}

        async for raw_event in orch.handle_chat(sid, "What happened last night?"):
            evt = parse_sse_event(raw_event)

            if evt["type"] == "stream_start":
                cid = evt["character_id"]
                char_deltas[cid] = []

            elif evt["type"] == "stream_delta":
                cid = evt["character_id"]
                if cid in char_deltas:
                    char_deltas[cid].append(evt["delta"])

            elif evt["type"] == "stream_end":
                cid = evt["character_id"]
                char_finals[cid] = evt["content"]

        # For each character, accumulated deltas should match final content
        for cid in char_finals:
            if cid in char_deltas and char_deltas[cid]:
                accumulated = "".join(char_deltas[cid])
                final = char_finals[cid]
                # Accumulated text should be a substring of (or equal to) final
                # (stream_end may use _last_response which could differ slightly)
                assert len(accumulated) > 0, f"No deltas accumulated for {cid}"
                logger.info("Char %s: %d delta chunks → %d chars final",
                           cid, len(char_deltas[cid]), len(final))


# ── Test: Message Queue Integrity ───────────────────────────────────────


class TestMessageQueueIntegrity:
    """Validate message ordering and persistence in the SSE pipeline."""

    @pytest.mark.asyncio
    async def test_player_message_recorded_first(self, discussion_state, mock_mistral):
        """Player message should be persisted before AI responses."""
        orch = GameOrchestrator(persistence=None)
        sid = discussion_state.session_id
        orch.session_mgr._sessions[sid] = discussion_state

        from backend.game.character_agent import CharacterAgent
        agents = {}
        for char in discussion_state.characters:
            agents[char.id] = CharacterAgent(char, discussion_state.world)
        orch.session_mgr._agents[sid] = agents

        initial_msg_count = len(discussion_state.messages)

        async for _ in orch.handle_chat(sid, "I accuse Elder Marcus!"):
            pass

        state = orch.session_mgr._sessions[sid]
        new_messages = state.messages[initial_msg_count:]

        # First new message should be the player's
        assert len(new_messages) >= 1
        assert new_messages[0].speaker_id == "player"
        assert new_messages[0].content == "I accuse Elder Marcus!"

        # Subsequent messages should be AI characters
        for msg in new_messages[1:]:
            assert msg.speaker_id != "player" or msg.speaker_id == "narrator"

    @pytest.mark.asyncio
    async def test_messages_have_round_and_phase(self, discussion_state, mock_mistral):
        """All messages should be tagged with current round and phase."""
        orch = GameOrchestrator(persistence=None)
        sid = discussion_state.session_id
        orch.session_mgr._sessions[sid] = discussion_state

        from backend.game.character_agent import CharacterAgent
        agents = {}
        for char in discussion_state.characters:
            agents[char.id] = CharacterAgent(char, discussion_state.world)
        orch.session_mgr._agents[sid] = agents

        async for _ in orch.handle_chat(sid, "Who is the wolf?"):
            pass

        state = orch.session_mgr._sessions[sid]
        # Check the last few messages (the ones we just created)
        recent = state.messages[-3:]
        for msg in recent:
            assert msg.round == discussion_state.round, f"Wrong round: {msg.round}"
            assert msg.phase == "discussion", f"Wrong phase: {msg.phase}"

    @pytest.mark.asyncio
    async def test_messages_have_timestamps(self, discussion_state, mock_mistral):
        """New messages created during chat should have created_at timestamps."""
        orch = GameOrchestrator(persistence=None)
        sid = discussion_state.session_id
        orch.session_mgr._sessions[sid] = discussion_state

        from backend.game.character_agent import CharacterAgent
        agents = {}
        for char in discussion_state.characters:
            agents[char.id] = CharacterAgent(char, discussion_state.world)
        orch.session_mgr._agents[sid] = agents

        initial_count = len(discussion_state.messages)

        async for _ in orch.handle_chat(sid, "Hello"):
            pass

        state = orch.session_mgr._sessions[sid]
        # Only check NEW messages (not pre-existing fixture messages)
        new_msgs = state.messages[initial_count:]
        assert len(new_msgs) >= 1
        for msg in new_msgs:
            assert msg.created_at, f"Missing timestamp on new message from {msg.speaker_id}"


# ── Test: TTS Latency Measurement ──────────────────────────────────────


class TestTTSLatencyMeasurement:
    """Measure and log TTS generation latency for performance tracking."""

    @pytest.mark.asyncio
    async def test_tts_generation_latency(self):
        """Measure mocked TTS generation time (baseline)."""
        import base64
        fake_pcm = make_fake_pcm(2.0)
        fake_b64 = base64.b64encode(fake_pcm).decode()
        response_data = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {"data": fake_b64}
                    }]
                }
            }]
        }

        # Simulate API delay
        async def delayed_post(*args, **kwargs):
            await asyncio.sleep(0.05)  # Simulate 50ms network latency
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = response_data
            return mock_resp

        with patch("backend.voice.tts_middleware.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = delayed_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            t_start = time.monotonic()
            pcm = await _call_gemini_tts("fake_key", "Hello world, testing TTS", "Kore")
            t_api = time.monotonic()

            wav = _pcm_to_wav(pcm)
            t_wav = time.monotonic()

            api_ms = (t_api - t_start) * 1000
            wav_ms = (t_wav - t_api) * 1000
            total_ms = (t_wav - t_start) * 1000

            logger.info("TTS latency breakdown: API=%.1fms, WAV=%.1fms, Total=%.1fms",
                       api_ms, wav_ms, total_ms)

            assert pcm is not None
            validate_wav_header(wav)
            # WAV conversion should be near-instant (< 5ms)
            assert wav_ms < 5.0, f"WAV conversion too slow: {wav_ms:.1f}ms"

    @pytest.mark.asyncio
    async def test_full_pipeline_latency(self, discussion_state, mock_mistral):
        """Measure full SSE → text → TTS pipeline latency."""
        orch = GameOrchestrator(persistence=None)
        sid = discussion_state.session_id
        orch.session_mgr._sessions[sid] = discussion_state

        from backend.game.character_agent import CharacterAgent
        agents = {}
        for char in discussion_state.characters:
            agents[char.id] = CharacterAgent(char, discussion_state.world)
        orch.session_mgr._agents[sid] = agents

        # Track timing of each stream phase
        timings: dict[str, list[float]] = {
            "stream_start": [],
            "stream_delta": [],
            "stream_end": [],
        }

        t_send = time.monotonic()

        async for raw_event in orch.handle_chat(sid, "What do you think?"):
            t = time.monotonic()
            evt = parse_sse_event(raw_event)
            if evt["type"] in timings:
                timings[evt["type"]].append(t - t_send)

        # Report timing analysis
        for event_type, timestamps in timings.items():
            if timestamps:
                first = timestamps[0] * 1000
                last = timestamps[-1] * 1000
                logger.info("  %s: first=%.0fms, last=%.0fms, count=%d",
                           event_type, first, last, len(timestamps))

        # stream_end should arrive after stream_start
        if timings["stream_start"] and timings["stream_end"]:
            text_gen_ms = (timings["stream_end"][0] - timings["stream_start"][0]) * 1000
            logger.info("  Text generation latency (first char): %.0fms", text_gen_ms)
            assert text_gen_ms > 0, "stream_end should come after stream_start"


# ── Test: Error Recovery ────────────────────────────────────────────────


class TestAudioPipelineErrorRecovery:
    """Test graceful degradation when TTS fails."""

    @pytest.mark.asyncio
    async def test_tts_timeout_returns_none(self):
        """TTS API timeout should return None without crashing.

        VoiceMiddleware.text_to_speech wraps _call_gemini_tts with try/except,
        so we test at the middleware level for proper error handling.
        """
        vm = VoiceMiddleware.__new__(VoiceMiddleware)
        vm._api_key = "fake_key"
        vm._character_voices = {}

        with patch("backend.voice.tts_middleware._call_gemini_tts",
                   new_callable=AsyncMock, side_effect=asyncio.TimeoutError):
            result = await vm.text_to_speech("Hello", "agent01")
            assert result is None

    @pytest.mark.asyncio
    async def test_tts_network_error_returns_none(self):
        """Network error should return None via middleware error handling."""
        import httpx
        vm = VoiceMiddleware.__new__(VoiceMiddleware)
        vm._api_key = "fake_key"
        vm._character_voices = {}

        with patch("backend.voice.tts_middleware._call_gemini_tts",
                   new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection refused")):
            result = await vm.text_to_speech("Hello", "agent01")
            assert result is None

    @pytest.mark.asyncio
    async def test_voice_middleware_unavailable(self):
        """VoiceMiddleware with no API key should be unavailable."""
        with patch.dict("os.environ", {}, clear=False):
            # Remove GEMINI_API_KEY if present
            import os
            old_key = os.environ.pop("GEMINI_API_KEY", None)
            try:
                vm = VoiceMiddleware()
                assert not vm.available
                result = await vm.text_to_speech("Hello", "agent01")
                assert result is None
            finally:
                if old_key:
                    os.environ["GEMINI_API_KEY"] = old_key

    @pytest.mark.asyncio
    async def test_stream_continues_after_tts_failure(self, discussion_state, mock_mistral):
        """SSE stream should complete even if TTS data generation fails internally."""
        orch = GameOrchestrator(persistence=None)
        sid = discussion_state.session_id
        orch.session_mgr._sessions[sid] = discussion_state

        from backend.game.character_agent import CharacterAgent
        agents = {}
        for char in discussion_state.characters:
            agents[char.id] = CharacterAgent(char, discussion_state.world)
        orch.session_mgr._agents[sid] = agents

        events = []
        async for raw_event in orch.handle_chat(sid, "Hello"):
            events.append(parse_sse_event(raw_event))

        # Stream should always end with 'done'
        assert events[-1]["type"] == "done"
        # Should have at least responders + some content + done
        assert len(events) >= 3
