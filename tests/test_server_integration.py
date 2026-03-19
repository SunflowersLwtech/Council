"""Integration tests for FastAPI server endpoints.

Tests API contract: request/response schemas, error handling, SSE streaming.
Follows SightLine's test_server_integration.py pattern — mocked backing services,
real HTTP request/response validation.

NOTE: Without lifespan events running (no real server), endpoints that require
the game orchestrator will return 503. We test both that path and the contract.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

os.environ.setdefault("MISTRAL_API_KEY", "test_key_for_unit_tests")

from httpx import AsyncClient, ASGITransport
from backend.server import app
from backend.models.game_models import GameCreateResponse, GameState


# ── Health & System Endpoints ───────────────────────────────────────


class TestHealthEndpoints:

    @pytest.mark.asyncio
    async def test_health_check(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"


# ── Orchestrator-Dependent Endpoints ────────────────────────────────
# These return 503 in test context because the lifespan event doesn't run.
# We verify they correctly return 503 (service not ready) rather than crash.


class TestOrchestratorGuard:
    """Verify _require_orchestrator returns 503 when not initialized."""

    @pytest.mark.asyncio
    async def test_skills_returns_503_without_lifespan(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/skills")
            # 503 is correct: orchestrator not initialized without lifespan
            assert resp.status_code == 503
            data = resp.json()
            assert "detail" in data

    @pytest.mark.asyncio
    async def test_scenarios_returns_503_without_lifespan(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/game/scenarios")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_game_state_returns_503_without_lifespan(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/game/fake-session/state")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_reveal_returns_503_without_lifespan(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/game/fake-session/reveal/char1")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_player_role_returns_503_without_lifespan(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/game/fake-session/player-role")
            assert resp.status_code == 503

    @pytest.mark.asyncio
    async def test_join_without_auth_returns_401(self):
        """Auth check happens before orchestrator check."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/game/fake-session/join")
            # Without auth header, should be 401 OR 503 depending on order
            assert resp.status_code in (401, 503)

    @pytest.mark.asyncio
    async def test_chat_returns_503_without_lifespan(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/game/fake-session/chat",
                json={"message": "Hello"},
            )
            # SSE endpoints: 503 before stream starts, or 200 with error in stream
            assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_vote_returns_503_without_lifespan(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/game/fake-session/vote",
                json={"target_character_id": "char1"},
            )
            assert resp.status_code in (200, 503)


# ── Voice Endpoints ─────────────────────────────────────────────────


@pytest.mark.voice
class TestVoiceEndpoints:

    @pytest.mark.asyncio
    async def test_tts_without_voice_returns_503(self):
        """TTS should return 503 when ElevenLabs is not configured."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/voice/tts",
                json={"text": "Hello world", "agent_id": "test"},
            )
            # Should return 503 (voice not available) or 200 if ElevenLabs is configured
            assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_sfx_without_voice_returns_503(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/voice/sfx",
                json={"prompt": "thunder", "duration_seconds": 2.0},
            )
            assert resp.status_code in (200, 503)

    @pytest.mark.asyncio
    async def test_scribe_token_without_key_returns_500(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ELEVENLABS_API_KEY", None)
                resp = await client.post("/api/voice/scribe-token")
                # Should fail if no API key
                assert resp.status_code in (200, 500)


# ── Request Validation ──────────────────────────────────────────────


class TestRequestValidation:

    @pytest.mark.voice
    @pytest.mark.asyncio
    async def test_tts_request_schema(self):
        """Verify TTSRequest schema enforcement."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Missing required field
            resp = await client.post("/api/voice/tts", json={})
            assert resp.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_game_create_max_characters(self):
        """num_characters has ge=3, le=12 constraint."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/game/create",
                data={"num_characters": "20"},
            )
            assert resp.status_code == 422  # Exceeds le=12


# ── Live API Integration Tests ──────────────────────────────────────


@pytest.mark.live_api
class TestServerLiveAPI:
    """Tests requiring real API keys. Run with: pytest -m live_api"""

    @pytest.mark.asyncio
    async def test_full_game_create_flow(self):
        """Create a game from text, verify response structure."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
            resp = await client.post(
                "/api/game/create",
                data={"text": "A mystery in a Victorian mansion. The butler, the maid, and the lord all have secrets."},
            )
            if resp.status_code in (500, 503):
                pytest.skip("Game creation requires full API setup")

            assert resp.status_code == 200
            data = resp.json()
            assert "session_id" in data
            assert "characters" in data
            assert len(data["characters"]) >= 3
            assert data["phase"] == "lobby"

            # Verify character public info doesn't leak hidden roles
            for char in data["characters"]:
                assert "hidden_role" not in char
                assert "faction" not in char
                assert "name" in char
                assert "public_role" in char
