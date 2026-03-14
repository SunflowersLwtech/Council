"""Session lifecycle management for COUNCIL game."""

import logging
import random
import asyncio
from datetime import datetime, timezone

from backend.models.game_models import (
    GameState, GameCreateResponse, CharacterPublicInfo,
    ChatMessage,
)
from backend.game.document_engine import DocumentEngine
from backend.game.character_factory import CharacterFactory
from backend.game.character_agent import CharacterAgent
from backend.game.game_master import GameMaster
from backend.game.skill_loader import SkillLoader, SkillConfig
from backend.game import state as game_state
from backend.game.persistence import PersistenceManager
from backend.game.player_role import (
    assign_player_role, get_player_night_action_type, get_eligible_night_targets,
)

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages game sessions, agents, and persistence."""

    def __init__(self, persistence: PersistenceManager | None = None):
        self.doc_engine = DocumentEngine()
        self.char_factory = CharacterFactory()
        self.skill_loader = SkillLoader()
        self.game_master = GameMaster(skill_loader=self.skill_loader)
        self.persistence = persistence
        # In-memory session storage
        self._sessions: dict[str, GameState] = {}
        self._agents: dict[str, dict[str, CharacterAgent]] = {}
        # Background tasks for fire-and-forget emotion updates
        self._bg_tasks: set[asyncio.Task] = set()

    # ── Session access ─────────────────────────────────────────────────

    async def get_session(self, session_id: str) -> GameState:
        # 1. Check in-memory cache
        state = self._sessions.get(session_id)
        if state:
            return state

        # 2. Try loading from Supabase/Redis
        if self.persistence and self.persistence.available:
            loaded = await self.persistence.load_game_state(session_id)
            if loaded:
                state_dict, agent_memory = loaded
                try:
                    state = GameState.model_validate(state_dict)
                    self._sessions[session_id] = state
                    self._reconstruct_agents(session_id, state, agent_memory)
                    logger.info("Session %s restored from Supabase", session_id)
                    return state
                except Exception as exc:
                    logger.warning("Failed to restore session %s: %s", session_id, exc)

        raise ValueError(f"Session {session_id} not found")

    def get_agents(self, session_id: str) -> dict[str, CharacterAgent]:
        return self._agents.get(session_id, {})

    def store_session(self, session_id: str, state: GameState):
        """Update the in-memory session cache."""
        self._sessions[session_id] = state

    # ── Agent memory ───────────────────────────────────────────────────

    def _extract_agent_memory(self, session_id: str) -> dict:
        """Extract serialisable memory from all agents for a session."""
        agents = self._agents.get(session_id, {})
        memory = {}
        for char_id, agent in agents.items():
            memory[char_id] = {
                "conversation_history": agent._conversation_history,
                "round_memory": agent._round_memory,
            }
        return memory

    def _resolve_session_skills(self, state: GameState) -> list[SkillConfig]:
        """Resolve active skills for a game session."""
        skill_ids = state.active_skills
        if not skill_ids:
            return []
        try:
            return self.skill_loader.resolve_skills(skill_ids)
        except ValueError as exc:
            logger.warning("Skill resolution failed: %s", exc)
            return []

    def _reconstruct_agents(
        self, session_id: str, state: GameState, agent_memory: dict
    ):
        """Rebuild CharacterAgent instances from GameState and restore their memory."""
        skills = self._resolve_session_skills(state)
        evil_factions = {
            f.get("name", "")
            for f in state.world.factions
            if f.get("alignment", "").lower() == "evil"
        }
        agents: dict[str, CharacterAgent] = {}
        for char in state.characters:
            agent = CharacterAgent(
                char, state.world,
                active_skills=skills,
                skill_loader=self.skill_loader,
                evil_factions=evil_factions,
                canon_facts=state.canon_facts,
            )
            mem = agent_memory.get(char.id, {})
            agent._conversation_history = mem.get("conversation_history", [])
            agent._round_memory = mem.get("round_memory", [])
            agents[char.id] = agent
        self._agents[session_id] = agents
        # Update game master with skills too
        self.game_master.set_skills(skills)

    # ── Persistence ────────────────────────────────────────────────────

    async def save_session(self, session_id: str):
        """Persist current session state to Supabase + agent memory to Redis cache."""
        if not self.persistence or not self.persistence.available:
            return
        state = self._sessions.get(session_id)
        if not state:
            return
        state_dict = state.model_dump(mode="json")
        agent_memory = self._extract_agent_memory(session_id)

        # Supabase: save game state metadata + all characters
        await self.persistence.save_game_state(session_id, state_dict)
        await self.persistence.save_characters(session_id, state.characters)

        # Redis: cache full state + agent memory for fast session recovery
        await self.persistence.save_redis_state(session_id, state_dict, agent_memory)

    async def persist_message(self, session_id: str, msg: ChatMessage):
        """Fire-and-forget: save a single message to Supabase."""
        if self.persistence and self.persistence.available:
            try:
                await self.persistence.save_message(session_id, msg)
            except Exception as exc:
                logger.warning("Message persistence failed: %s", exc)

    async def persist_vote(self, session_id: str, vote, round_num: int):
        """Fire-and-forget: save a single vote to Supabase."""
        if self.persistence and self.persistence.available:
            try:
                await self.persistence.save_vote(session_id, vote, round_num)
            except Exception as exc:
                logger.warning("Vote persistence failed: %s", exc)

    async def persist_night_action(self, session_id: str, action, round_num: int):
        """Fire-and-forget: save a single night action to Supabase."""
        if self.persistence and self.persistence.available:
            try:
                await self.persistence.save_night_action(session_id, action, round_num)
            except Exception as exc:
                logger.warning("Night action persistence failed: %s", exc)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def stamp_message(msg: ChatMessage, emotion: str = "") -> ChatMessage:
        """Set created_at timestamp and optional dominant_emotion on a ChatMessage."""
        if not msg.created_at:
            msg.created_at = datetime.now(timezone.utc).isoformat()
        if emotion:
            msg.dominant_emotion = emotion
        return msg

    @staticmethod
    def display_chunks(text: str, chunk_size: int = 3):
        """Split text into small visual chunks for smoother frontend streaming."""
        if not text:
            return
        i = 0
        n = len(text)
        while i < n:
            end = min(i + chunk_size, n)
            yield text[i:end]
            i = end

    def public_state(self, state: GameState, full: bool = False) -> dict:
        """Build public projection of game state (no hidden info)."""
        chars = [
            CharacterPublicInfo(
                id=c.id, name=c.name, persona=c.persona,
                speaking_style=c.speaking_style, avatar_seed=c.avatar_seed,
                public_role=c.public_role, voice_id=c.voice_id,
                is_eliminated=c.is_eliminated,
                is_player=getattr(c, 'is_player', False),
            )
            for c in state.characters
        ]
        messages = state.messages if full else state.messages[-50:]
        result = {
            "session_id": state.session_id,
            "phase": state.phase,
            "round": state.round,
            "world_title": state.world.title,
            "world_setting": state.world.setting,
            "flavor_text": state.world.flavor_text,
            "characters": [c.model_dump() for c in chars],
            "eliminated": state.eliminated,
            "messages": [m.model_dump() for m in messages],
            "vote_results": [vr.model_dump() for vr in state.vote_results],
            "winner": state.winner,
        }
        # Include player role info (safe — only player's own data)
        if state.player_role:
            pr = state.player_role
            ally_details = []
            for aid in pr.allies:
                achar = next((c for c in state.characters if c.id == aid), None)
                if achar and not achar.is_eliminated:
                    ally_details.append({"id": aid, "name": achar.name})
            result["player_role"] = {
                "hidden_role": pr.hidden_role,
                "faction": pr.faction,
                "win_condition": pr.win_condition,
                "allies": ally_details,
                "is_eliminated": pr.is_eliminated,
                "eliminated_by": pr.eliminated_by,
            }

        # Include pending night action prompt for session recovery
        if full and state.awaiting_player_night_action:
            action_type = get_player_night_action_type(state)
            if action_type:
                result["night_action_prompt"] = {
                    "action_type": action_type,
                    "eligible_targets": get_eligible_night_targets(state),
                }

        return result

    def fire_and_forget(self, coro):
        """Schedule a coroutine as a fire-and-forget background task."""
        task = asyncio.ensure_future(coro)
        self._bg_tasks.add(task)

        def _done(t):
            self._bg_tasks.discard(t)
            if not t.cancelled():
                exc = t.exception()
                if exc:
                    logger.warning("Background task failed: %s", exc)

        task.add_done_callback(_done)

    # ── Session creation ───────────────────────────────────────────────

    async def create_session_from_file(
        self, file_bytes: bytes, filename: str, num_characters: int | None = None,
        enabled_skills: list[str] | None = None, language: str | None = None,
    ) -> GameCreateResponse:
        """Create a game from an uploaded document."""
        world = await self.doc_engine.process_document(file_bytes, filename)
        return await self._finalize_session(world, num_characters, enabled_skills, language)

    async def create_session_from_text(
        self, text: str, num_characters: int | None = None,
        enabled_skills: list[str] | None = None, language: str | None = None,
    ) -> GameCreateResponse:
        """Create a game from raw text."""
        world = await self.doc_engine.process_text(text)
        return await self._finalize_session(world, num_characters, enabled_skills, language)

    async def create_session_from_scenario(
        self, scenario_id: str, num_characters: int | None = None,
        enabled_skills: list[str] | None = None,
    ) -> GameCreateResponse:
        """Create a game from a pre-built scenario."""
        world = await self.doc_engine.load_scenario(scenario_id)
        return await self._finalize_session(world, num_characters, enabled_skills)

    async def _finalize_session(
        self, world, num_characters: int | None = None,
        enabled_skills: list[str] | None = None,
        language: str | None = None,
    ) -> GameCreateResponse:
        """Generate characters, create agents, store session."""
        count = num_characters if num_characters is not None else world.recommended_player_count
        characters = await self.char_factory.generate_characters(world, count, language=language)

        # Resolve skills — use all available skills by default
        skill_ids = enabled_skills if enabled_skills is not None else self.skill_loader.all_skill_ids()
        try:
            active_skills = self.skill_loader.resolve_skills(skill_ids)
        except ValueError as exc:
            logger.warning("Skill resolution failed, starting without skills: %s", exc)
            active_skills = []

        state = GameState(
            world=world,
            characters=characters,
            active_skills=[s.id for s in active_skills],
            language=language,
        )

        # Establish canon facts from world setup
        state.canon_facts.append(f"World: {world.title}")
        state.canon_facts.append(f"Setting: {world.setting}")
        for faction in world.factions:
            state.canon_facts.append(f"Faction '{faction.get('name', '?')}' is {faction.get('alignment', '?')}")
        for char in characters:
            state.canon_facts.append(f"{char.name} is publicly known as {char.public_role}")

        # ── Assign player a hidden role ──────────────────────────────
        player_role = assign_player_role(state, world, characters)
        state.player_role = player_role
        state.canon_facts.append("You (the player) are publicly known as a Council Member")
        if language:
            state.canon_facts.append(f"LANGUAGE: All dialogue and narration must be in {language}")

        self._sessions[state.session_id] = state

        # Update game master with active skills
        self.game_master.set_skills(active_skills)

        # Compute evil factions once for all agents
        evil_factions = {
            f.get("name", "")
            for f in world.factions
            if f.get("alignment", "").lower() == "evil"
        }

        # Create character agents with active skills and faction-aware injection
        agents = {}
        for char in characters:
            agent = CharacterAgent(
                char, world,
                active_skills=active_skills,
                skill_loader=self.skill_loader,
                evil_factions=evil_factions,
                canon_facts=state.canon_facts,
            )
            # If player is evil, inform evil AI allies about the player
            if player_role and player_role.faction == char.faction:
                if char.faction in evil_factions:
                    ally_note = (
                        f"The player (You) is secretly your ally — "
                        f"they are a {player_role.hidden_role} of the {player_role.faction}. "
                        f"Do NOT target the player during night actions."
                    )
                    char.hidden_knowledge.append(ally_note)
                    # Rebuild agent prompt to include the new knowledge
                    agent = CharacterAgent(
                        char, world,
                        active_skills=active_skills,
                        skill_loader=self.skill_loader,
                        evil_factions=evil_factions,
                        canon_facts=state.canon_facts,
                    )
            agents[char.id] = agent
        self._agents[state.session_id] = agents

        chars_public = [
            CharacterPublicInfo(
                id=c.id, name=c.name, persona=c.persona,
                speaking_style=c.speaking_style, avatar_seed=c.avatar_seed,
                public_role=c.public_role, voice_id=c.voice_id,
                is_eliminated=c.is_eliminated,
                is_player=getattr(c, 'is_player', False),
            )
            for c in characters
        ]

        await self.save_session(state.session_id)

        return GameCreateResponse(
            session_id=state.session_id,
            world_title=world.title,
            world_setting=world.setting,
            characters=chars_public,
            phase=state.phase,
        )

    # ── Game flow (non-streaming) ──────────────────────────────────────

    async def start_game(self, session_id: str) -> dict:
        """Transition from lobby to discussion and return narration."""
        state = await self.get_session(session_id)
        agents = self.get_agents(session_id)
        state, narration = await self.game_master.advance_phase(state, agents)
        self._sessions[session_id] = state
        await self.save_session(session_id)

        return {
            "phase": state.phase,
            "round": state.round,
            "narration": narration,
            "has_player_role": state.player_role is not None,
        }

    # ── Queries ────────────────────────────────────────────────────────

    async def get_public_state(self, session_id: str, full: bool = False) -> dict:
        """Return the public projection of game state."""
        state = await self.get_session(session_id)
        return self.public_state(state, full=full)

    async def get_reveal(self, session_id: str, character_id: str) -> dict:
        """Get an eliminated character's hidden info."""
        state = await self.get_session(session_id)
        char = next((c for c in state.characters if c.id == character_id), None)
        if not char:
            raise ValueError(f"Character {character_id} not found")
        if not char.is_eliminated:
            raise ValueError(f"Character {character_id} is not eliminated")
        return {
            "id": char.id,
            "name": char.name,
            "hidden_role": char.hidden_role,
            "faction": char.faction,
            "win_condition": char.win_condition,
            "hidden_knowledge": char.hidden_knowledge,
            "behavioral_rules": char.behavioral_rules,
        }

    async def get_player_role(self, session_id: str) -> dict:
        """Get the player's hidden role (only visible to the player)."""
        state = await self.get_session(session_id)
        if not state.player_role:
            raise ValueError("No player role assigned")
        pr = state.player_role
        ally_details = []
        for aid in pr.allies:
            achar = next((c for c in state.characters if c.id == aid), None)
            if achar:
                ally_details.append({"id": aid, "name": achar.name})
        return {
            "hidden_role": pr.hidden_role,
            "faction": pr.faction,
            "win_condition": pr.win_condition,
            "allies": ally_details,
            "is_eliminated": pr.is_eliminated,
            "eliminated_by": pr.eliminated_by,
        }

    def list_scenarios(self) -> list[dict]:
        """List available pre-built scenarios."""
        return self.doc_engine.list_scenarios()

    # ── Multiplayer ────────────────────────────────────────────────────

    async def join_game(self, session_id: str, user_id: str) -> dict:
        """Assign a human player to an unoccupied character."""
        state = await self.get_session(session_id)

        # Only allow joining during lobby phase
        if state.phase not in ("lobby", "discussion"):
            raise ValueError(f"Cannot join game in '{state.phase}' phase")

        # Check if this user already joined (idempotent)
        existing = next((c for c in state.characters if c.player_user_id == user_id), None)
        if existing:
            return {
                "character_id": existing.id,
                "name": existing.name,
                "public_role": existing.public_role,
                "persona": existing.persona,
                "avatar_seed": existing.avatar_seed,
            }

        # Find unoccupied, non-eliminated character
        available = [c for c in state.characters if not c.is_player and not c.is_eliminated]
        if not available:
            raise ValueError("No available characters to join")

        char = random.choice(available)
        char.is_player = True
        char.player_user_id = user_id

        # _save_session handles both Supabase and Redis persistence
        self._sessions[session_id] = state
        await self.save_session(session_id)

        return {
            "character_id": char.id,
            "name": char.name,
            "public_role": char.public_role,
            "persona": char.persona,
            "avatar_seed": char.avatar_seed,
        }
