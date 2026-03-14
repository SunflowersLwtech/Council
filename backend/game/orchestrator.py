"""GameOrchestrator — thin facade delegating to focused modules.

All public methods preserve their existing signatures so that
server.py requires zero modifications.
"""

from typing import AsyncGenerator

from backend.game.session_manager import SessionManager
from backend.game.persistence import PersistenceManager
from backend.game.phase_handlers import discussion, voting, night


class GameOrchestrator:
    """Thin facade — delegates to SessionManager and phase handlers."""

    def __init__(self, persistence: PersistenceManager | None = None):
        self.session_mgr = SessionManager(persistence=persistence)
        # Expose sub-objects that server.py accesses directly
        self.skill_loader = self.session_mgr.skill_loader
        self._sessions = self.session_mgr._sessions

    # ── Session creation ───────────────────────────────────────────────

    async def create_session_from_file(
        self, file_bytes: bytes, filename: str, num_characters: int | None = None,
        enabled_skills: list[str] | None = None, language: str | None = None,
    ):
        return await self.session_mgr.create_session_from_file(
            file_bytes, filename, num_characters,
            enabled_skills=enabled_skills, language=language,
        )

    async def create_session_from_text(
        self, text: str, num_characters: int | None = None,
        enabled_skills: list[str] | None = None, language: str | None = None,
    ):
        return await self.session_mgr.create_session_from_text(
            text, num_characters, enabled_skills=enabled_skills, language=language,
        )

    async def create_session_from_scenario(
        self, scenario_id: str, num_characters: int | None = None,
        enabled_skills: list[str] | None = None,
    ):
        return await self.session_mgr.create_session_from_scenario(
            scenario_id, num_characters, enabled_skills=enabled_skills,
        )

    # ── Game flow (non-streaming) ──────────────────────────────────────

    async def start_game(self, session_id: str) -> dict:
        return await self.session_mgr.start_game(session_id)

    # ── Discussion ─────────────────────────────────────────────────────

    async def handle_open_discussion(self, session_id: str) -> AsyncGenerator[str, None]:
        async for event in discussion.handle_open_discussion(self.session_mgr, session_id):
            yield event

    async def handle_chat(
        self, session_id: str, message: str, target_character_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        async for event in discussion.handle_chat(
            self.session_mgr, session_id, message, target_character_id,
        ):
            yield event

    # ── Voting ─────────────────────────────────────────────────────────

    async def handle_vote(
        self, session_id: str, target_character_id: str,
    ) -> AsyncGenerator[str, None]:
        async for event in voting.handle_vote(
            self.session_mgr, session_id, target_character_id,
        ):
            yield event

    # ── Night ──────────────────────────────────────────────────────────

    async def handle_night(self, session_id: str) -> AsyncGenerator[str, None]:
        async for event in night.handle_night(self.session_mgr, session_id):
            yield event

    async def handle_night_chat(
        self, session_id: str, message: str,
    ) -> AsyncGenerator[str, None]:
        async for event in night.handle_night_chat(self.session_mgr, session_id, message):
            yield event

    async def handle_player_night_action(
        self, session_id: str, action_type: str, target_character_id: str,
    ) -> AsyncGenerator[str, None]:
        async for event in night.handle_player_night_action(
            self.session_mgr, session_id, action_type, target_character_id,
        ):
            yield event

    # ── Queries ─────────────────────────────────────────────────────────

    async def get_public_state(self, session_id: str, full: bool = False) -> dict:
        return await self.session_mgr.get_public_state(session_id, full=full)

    async def get_reveal(self, session_id: str, character_id: str) -> dict:
        return await self.session_mgr.get_reveal(session_id, character_id)

    async def get_player_role(self, session_id: str) -> dict:
        return await self.session_mgr.get_player_role(session_id)

    def list_scenarios(self) -> list[dict]:
        return self.session_mgr.list_scenarios()

    # ── Multiplayer ────────────────────────────────────────────────────

    async def join_game(self, session_id: str, user_id: str) -> dict:
        return await self.session_mgr.join_game(session_id, user_id)
