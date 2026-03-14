"""PersistenceManager — Supabase (primary) + Redis (cache) storage for game sessions."""

import os
import json
import asyncio
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TTL_SECONDS = 86400  # 24 hours


class PersistenceManager:
    """Supabase-first persistence with optional Redis cache for agent memory.

    All public methods are wrapped in try/except — failures log warnings
    but never crash the game (falls back to in-memory only).
    """

    def __init__(self):
        self._redis = None
        self._supabase = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def connect(self):
        """Initialise Supabase and Redis clients from env vars."""
        # Supabase (primary)
        sb_url = os.environ.get("SUPABASE_URL")
        sb_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        if sb_url and sb_key:
            try:
                from supabase import create_client
                self._supabase = create_client(sb_url, sb_key)
                logger.info("Supabase connected")
            except Exception as exc:
                logger.warning("Supabase connection failed: %s", exc)
                self._supabase = None
        else:
            logger.warning("SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY not set — Supabase disabled")

        # Redis (optional cache for agent memory)
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    redis_url, decode_responses=True, socket_timeout=5
                )
                await self._redis.ping()
                logger.info("Redis connected (cache)")
            except Exception as exc:
                logger.warning("Redis connection failed: %s", exc)
                self._redis = None
        else:
            logger.info("REDIS_URL not set — Redis cache disabled (Supabase-only mode)")

    async def close(self):
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass

    @property
    def available(self) -> bool:
        return self._supabase is not None

    # ── Supabase: Game Sessions ────────────────────────────────────────

    async def save_game_state(self, session_id: str, state_dict: dict):
        """Upsert game session metadata to Supabase."""
        if not self._supabase:
            return
        try:
            now = datetime.now(timezone.utc).isoformat()
            row = {
                "session_id": session_id,
                "world_title": state_dict.get("world", {}).get("title", ""),
                "phase": state_dict.get("phase", "lobby"),
                "round": state_dict.get("round", 1),
                "player_count": len(state_dict.get("characters", [])),
                "winner": state_dict.get("winner"),
                "is_active": state_dict.get("phase") != "ended",
                "tension_level": state_dict.get("tension_level", 0.3),
                "awaiting_player_night_action": state_dict.get("awaiting_player_night_action", False),
                "active_skills": state_dict.get("active_skills", []),
                "updated_at": now,
            }
            await asyncio.to_thread(
                lambda: self._supabase.table("game_sessions").upsert(
                    row, on_conflict="session_id"
                ).execute()
            )
        except Exception as exc:
            logger.warning("Supabase save_game_state failed for %s: %s", session_id, exc)

    async def save_characters(self, session_id: str, characters):
        """Batch upsert characters to Supabase game_characters table.

        Args:
            characters: list of Character model instances (or dicts).
        """
        if not self._supabase:
            return
        try:
            now = datetime.now(timezone.utc).isoformat()
            rows = []
            for char in characters:
                # Support both model instances and dicts
                if hasattr(char, "model_dump"):
                    c = char.model_dump(mode="json")
                else:
                    c = char

                rows.append({
                    "id": c.get("id", str(uuid.uuid4())[:8]),
                    "session_id": session_id,
                    "player_user_id": c.get("player_user_id"),
                    "name": c.get("name", ""),
                    "public_role": c.get("public_role", ""),
                    "persona": c.get("persona", ""),
                    "avatar": c.get("avatar_seed", ""),
                    "speaking_style": c.get("speaking_style", ""),
                    "is_eliminated": c.get("is_eliminated", False),
                    "faction": c.get("faction", ""),
                    "hidden_role": c.get("hidden_role", ""),
                    "win_condition": c.get("win_condition", ""),
                    "hidden_knowledge": json.dumps(c.get("hidden_knowledge", [])) if isinstance(c.get("hidden_knowledge"), list) else str(c.get("hidden_knowledge", "")),
                    "emotional_state": c.get("emotional_state", {}),
                    "relationships": [r if isinstance(r, dict) else r for r in c.get("relationships", [])],
                    "is_player": c.get("is_player", False),
                    "updated_at": now,
                })
            if rows:
                await asyncio.to_thread(
                    lambda: self._supabase.table("game_characters").upsert(
                        rows, on_conflict="id"
                    ).execute()
                )
        except Exception as exc:
            logger.warning("Supabase save_characters failed for %s: %s", session_id, exc)

    async def save_message(self, session_id: str, msg):
        """Insert a single chat message to Supabase game_messages table.

        Args:
            msg: ChatMessage model instance or dict.
        """
        if not self._supabase:
            return
        try:
            if hasattr(msg, "model_dump"):
                m = msg.model_dump(mode="json")
            else:
                m = msg

            row = {
                "id": m.get("id", str(uuid.uuid4())),
                "session_id": session_id,
                "speaker_id": m.get("speaker_id", ""),
                "speaker_name": m.get("speaker_name", ""),
                "content": m.get("content", ""),
                "is_public": m.get("is_public", True),
                "phase": m.get("phase", ""),
                "round": m.get("round", 0),
                "message_type": m.get("message_type", "chat"),
                "dominant_emotion": m.get("dominant_emotion", ""),
                "created_at": m.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
            await asyncio.to_thread(
                lambda: self._supabase.table("game_messages").upsert(
                    row, on_conflict="id"
                ).execute()
            )
        except Exception as exc:
            logger.warning("Supabase save_message failed for %s: %s", session_id, exc)

    async def save_vote(self, session_id: str, vote, round_num: int):
        """Insert a vote record to Supabase game_votes table.

        Args:
            vote: VoteRecord model instance or dict.
            round_num: current game round.
        """
        if not self._supabase:
            return
        try:
            if hasattr(vote, "model_dump"):
                v = vote.model_dump(mode="json")
            else:
                v = vote

            row = {
                "id": v.get("id", str(uuid.uuid4())),
                "session_id": session_id,
                "round": round_num,
                "voter_id": v.get("voter_id", ""),
                "voter_name": v.get("voter_name", ""),
                "target_id": v.get("target_id", ""),
                "target_name": v.get("target_name", ""),
                "reasoning": v.get("reasoning", ""),
                "created_at": v.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
            await asyncio.to_thread(
                lambda: self._supabase.table("game_votes").upsert(
                    row, on_conflict="id"
                ).execute()
            )
        except Exception as exc:
            logger.warning("Supabase save_vote failed for %s: %s", session_id, exc)

    async def save_night_action(self, session_id: str, action, round_num: int):
        """Insert a night action record to Supabase game_night_actions table.

        Args:
            action: NightAction model instance or dict.
            round_num: current game round.
        """
        if not self._supabase:
            return
        try:
            if hasattr(action, "model_dump"):
                a = action.model_dump(mode="json")
            else:
                a = action

            row = {
                "id": a.get("id", str(uuid.uuid4())),
                "session_id": session_id,
                "round": round_num,
                "character_id": a.get("character_id", ""),
                "character_name": a.get("character_name", ""),
                "action_type": a.get("action_type", ""),
                "target_id": a.get("target_id"),
                "result": a.get("result", ""),
                "created_at": a.get("created_at") or datetime.now(timezone.utc).isoformat(),
            }
            await asyncio.to_thread(
                lambda: self._supabase.table("game_night_actions").upsert(
                    row, on_conflict="id"
                ).execute()
            )
        except Exception as exc:
            logger.warning("Supabase save_night_action failed for %s: %s", session_id, exc)

    # ── Supabase: Load & Query ─────────────────────────────────────────

    async def load_game_state(self, session_id: str) -> tuple[dict, dict] | None:
        """Load game state from Supabase + optional Redis agent memory.

        Returns (state_dict, agent_memory) or None.
        """
        if not self._supabase:
            return None

        try:
            # Load session
            result = await asyncio.to_thread(
                lambda: self._supabase.table("game_sessions")
                .select("*")
                .eq("session_id", session_id)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )
            session_row = result.data
            if not session_row:
                return None

            # Load characters
            chars_result = await asyncio.to_thread(
                lambda: self._supabase.table("game_characters")
                .select("*")
                .eq("session_id", session_id)
                .execute()
            )
            characters = []
            for row in (chars_result.data or []):
                characters.append({
                    "id": row.get("id", ""),
                    "name": row.get("name", ""),
                    "persona": row.get("persona", ""),
                    "speaking_style": row.get("speaking_style", ""),
                    "avatar_seed": row.get("avatar", ""),
                    "public_role": row.get("public_role", ""),
                    "hidden_role": row.get("hidden_role", ""),
                    "faction": row.get("faction", ""),
                    "win_condition": row.get("win_condition", ""),
                    "hidden_knowledge": _parse_json_or_list(row.get("hidden_knowledge", "[]")),
                    "is_eliminated": row.get("is_eliminated", False),
                    "emotional_state": row.get("emotional_state", {}),
                    "relationships": row.get("relationships", []),
                    "is_player": row.get("is_player", False),
                    "player_user_id": row.get("player_user_id"),
                })

            # Load messages
            msgs_result = await asyncio.to_thread(
                lambda: self._supabase.table("game_messages")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at")
                .execute()
            )
            messages = []
            for row in (msgs_result.data or []):
                messages.append({
                    "id": row.get("id", ""),
                    "speaker_id": row.get("speaker_id", ""),
                    "speaker_name": row.get("speaker_name", ""),
                    "content": row.get("content", ""),
                    "is_public": row.get("is_public", True),
                    "phase": row.get("phase", ""),
                    "round": row.get("round", 0),
                    "message_type": row.get("message_type", "chat"),
                    "dominant_emotion": row.get("dominant_emotion", ""),
                    "created_at": row.get("created_at", ""),
                })

            # Build state dict
            state_dict = {
                "session_id": session_id,
                "phase": session_row.get("phase", "lobby"),
                "round": session_row.get("round", 1),
                "world": {"title": session_row.get("world_title", "")},
                "characters": characters,
                "messages": messages,
                "winner": session_row.get("winner"),
                "tension_level": session_row.get("tension_level", 0.3),
                "awaiting_player_night_action": session_row.get("awaiting_player_night_action", False),
                "active_skills": session_row.get("active_skills", []),
            }

            # Try loading agent memory from Redis
            agent_memory = {}
            if self._redis:
                try:
                    agents_raw = await self._redis.get(f"game:{session_id}:agents")
                    if agents_raw:
                        agent_memory = json.loads(agents_raw)
                except Exception:
                    pass

            return state_dict, agent_memory

        except Exception as exc:
            logger.warning("Supabase load_game_state failed for %s: %s", session_id, exc)
            return None

    async def session_exists(self, session_id: str) -> bool:
        """Check if an active session exists in Supabase."""
        if not self._supabase:
            return False
        try:
            result = await asyncio.to_thread(
                lambda: self._supabase.table("game_sessions")
                .select("session_id")
                .eq("session_id", session_id)
                .eq("is_active", True)
                .execute()
            )
            return bool(result.data)
        except Exception:
            return False

    async def delete_game_state(self, session_id: str):
        """Mark session as inactive in Supabase + clean up Redis cache."""
        if self._supabase:
            try:
                await asyncio.to_thread(
                    lambda: self._supabase.table("game_sessions").update(
                        {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}
                    ).eq("session_id", session_id).execute()
                )
            except Exception as exc:
                logger.warning("Supabase deactivate failed for %s: %s", session_id, exc)

        if self._redis:
            try:
                await self._redis.delete(
                    f"game:{session_id}:state",
                    f"game:{session_id}:agents",
                )
            except Exception as exc:
                logger.warning("Redis delete failed for %s: %s", session_id, exc)

    # ── Redis: Agent Memory Cache ──────────────────────────────────────

    async def save_agent_memory(self, session_id: str, agent_memory: dict):
        """Cache agent conversation history in Redis (for fast restoration)."""
        if not self._redis:
            return
        try:
            agents_key = f"game:{session_id}:agents"
            await self._redis.set(agents_key, json.dumps(agent_memory), ex=TTL_SECONDS)
        except Exception as exc:
            logger.warning("Redis save_agent_memory failed for %s: %s", session_id, exc)

    async def save_redis_state(
        self, session_id: str, state_dict: dict, agent_memory: dict
    ):
        """Write full state + agent memory to Redis cache (for fast session recovery)."""
        if not self._redis:
            return
        try:
            state_key = f"game:{session_id}:state"
            agents_key = f"game:{session_id}:agents"
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.set(state_key, json.dumps(state_dict), ex=TTL_SECONDS)
                pipe.set(agents_key, json.dumps(agent_memory), ex=TTL_SECONDS)
                await pipe.execute()
        except Exception as exc:
            logger.warning("Redis save failed for %s: %s", session_id, exc)


def _parse_json_or_list(val) -> list:
    """Parse a JSON string into a list, or return as-is if already a list."""
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except (json.JSONDecodeError, ValueError):
            return [val] if val else []
    return []
