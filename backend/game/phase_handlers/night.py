"""Night phase handler."""

import random
import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator

from backend.models.game_models import ChatMessage, NightAction
from backend.game import state as game_state
from backend.game import sse_emitter as sse
from backend.game.player_role import get_player_night_action_type, get_eligible_night_targets
from backend.voice.tts_middleware import inject_emotion_tags

STREAM_DELTA_PACE_SEC = 0.04


async def handle_night(session_mgr, session_id: str) -> AsyncGenerator[str, None]:
    """Handle the night phase. Yields SSE event strings."""
    state = await session_mgr.get_session(session_id)
    agents = session_mgr.get_agents(session_id)

    if state.phase != "night":
        yield sse.error("Not in night phase")
        return

    yield sse.night_started()

    # Check if player needs to act
    player_action_type = get_player_night_action_type(state)
    if player_action_type:
        # Emit prompt for player to choose their night action
        eligible_targets = get_eligible_night_targets(state)
        # Include ally info so evil players know their teammates
        allies = []
        if state.player_role and state.player_role.allies:
            for aid in state.player_role.allies:
                achar = next((c for c in state.characters if c.id == aid and not c.is_eliminated), None)
                if achar:
                    allies.append({"id": aid, "name": achar.name, "avatar_seed": achar.avatar_seed})

        # Evil players: allies auto-suggest kill targets before player chooses
        if player_action_type == "kill" and state.player_role:
            alive = game_state.get_alive_characters(state)
            for aid in state.player_role.allies:
                ally_char = next((c for c in alive if c.id == aid), None)
                agent = agents.get(aid)
                if not ally_char or not agent:
                    continue
                suggestion_prompt = (
                    "Night has fallen. Whisper to your allies: "
                    "who do you think we should eliminate tonight? "
                    "Base your suggestion on today's discussion. 1-2 sentences only."
                )
                yield sse.thinking(ally_char.id, ally_char.name)
                yield sse.stream_start(ally_char.id, ally_char.name)
                full = ""
                try:
                    async for chunk in agent.respond_stream(
                        suggestion_prompt, state.messages,
                        talk_modifier="[NIGHT WHISPER - ALLIES ONLY] Speak freely about kill strategy.",
                    ):
                        full += chunk
                        for delta in session_mgr.display_chunks(chunk):
                            yield sse.stream_delta(ally_char.id, delta)
                            await asyncio.sleep(STREAM_DELTA_PACE_SEC)
                except Exception:
                    if not full:
                        full = agent._get_fallback_response()
                response = getattr(agent, '_last_response', None) or full
                dominant_emotion = agent.get_dominant_emotion()
                tts_text = inject_emotion_tags(response, ally_char.emotional_state)
                yield sse.stream_end(
                    ally_char.id, ally_char.name, response,
                    tts_text, ally_char.voice_id, dominant_emotion,
                )
                night_msg = ChatMessage(
                    speaker_id=ally_char.id, speaker_name=ally_char.name,
                    content=response, is_public=False, phase="night", round=state.round,
                )
                session_mgr.stamp_message(night_msg, emotion=dominant_emotion)
                state.messages.append(night_msg)
                await session_mgr.persist_message(session_id, night_msg)

        yield sse.night_action_prompt(player_action_type, eligible_targets, allies)
        # Mark state as awaiting player action and return
        state.awaiting_player_night_action = True
        session_mgr.store_session(session_id, state)
        await session_mgr.save_session(session_id)
        yield sse.done(phase="night")
        return

    # Player has no night action (villager) — resolve immediately
    async for event in _resolve_night(session_mgr, session_id, player_action=None):
        yield event


async def handle_night_chat(
    session_mgr, session_id: str, message: str,
) -> AsyncGenerator[str, None]:
    """Handle player chat with evil allies during night. Yields SSE event strings."""
    state = await session_mgr.get_session(session_id)
    agents = session_mgr.get_agents(session_id)

    if state.phase != "night" or not state.awaiting_player_night_action:
        yield sse.error("Night chat not available")
        return

    # Record player message
    player_whisper = ChatMessage(
        speaker_id="player", speaker_name="You", content=message,
        is_public=False, phase="night", round=state.round,
    )
    session_mgr.stamp_message(player_whisper)
    state.messages.append(player_whisper)
    await session_mgr.persist_message(session_id, player_whisper)

    # Get alive evil allies to respond
    alive = game_state.get_alive_characters(state)
    ally_ids = set(state.player_role.allies) if state.player_role else set()
    allies = [c for c in alive if c.id in ally_ids]

    for ally in allies:
        agent = agents.get(ally.id)
        if not agent:
            continue
        yield sse.thinking(ally.id, ally.name)
        yield sse.stream_start(ally.id, ally.name)
        full = ""
        try:
            async for chunk in agent.respond_stream(
                message, state.messages,
                talk_modifier="[NIGHT WHISPER - ALLIES ONLY] Respond to your ally's message. Discuss kill strategy freely. 1-2 sentences.",
            ):
                full += chunk
                for delta in session_mgr.display_chunks(chunk):
                    yield sse.stream_delta(ally.id, delta)
                    await asyncio.sleep(STREAM_DELTA_PACE_SEC)
        except Exception:
            if not full:
                full = agent._get_fallback_response()
        response = getattr(agent, '_last_response', None) or full
        dominant_emotion = agent.get_dominant_emotion()
        tts_text = inject_emotion_tags(response, ally.emotional_state)
        yield sse.stream_end(ally.id, ally.name, response, tts_text, ally.voice_id, dominant_emotion)
        ally_msg = ChatMessage(
            speaker_id=ally.id, speaker_name=ally.name,
            content=response, is_public=False, phase="night", round=state.round,
        )
        session_mgr.stamp_message(ally_msg, emotion=dominant_emotion)
        state.messages.append(ally_msg)
        await session_mgr.persist_message(session_id, ally_msg)

    session_mgr.store_session(session_id, state)
    await session_mgr.save_session(session_id)
    yield sse.done(phase="night")


async def handle_player_night_action(
    session_mgr, session_id: str, action_type: str, target_character_id: str,
) -> AsyncGenerator[str, None]:
    """Handle the player's submitted night action, then resolve all night actions."""
    state = await session_mgr.get_session(session_id)

    if not state.awaiting_player_night_action:
        yield sse.error("Not awaiting player night action")
        return

    state.awaiting_player_night_action = False
    session_mgr.store_session(session_id, state)

    player_action = NightAction(
        character_id="player",
        action_type=action_type,
        target_id=target_character_id,
    )

    async for event in _resolve_night(session_mgr, session_id, player_action=player_action):
        yield event


async def _resolve_night(
    session_mgr, session_id: str, player_action: NightAction | None = None,
) -> AsyncGenerator[str, None]:
    """Resolve all night actions (AI + player) and emit SSE events."""
    state = await session_mgr.get_session(session_id)
    agents = session_mgr.get_agents(session_id)

    # Execute night phase via game master (includes player action)
    state, narration_text = await session_mgr.game_master.handle_night(
        state, agents, player_action=player_action,
    )

    # Persist and emit individual night actions
    for action in state.night_actions:
        # Set character_name if not already set
        if not action.character_name and action.character_id != "player":
            char_match = next((c for c in state.characters if c.id == action.character_id), None)
            if char_match:
                action.character_name = char_match.name
        if not action.created_at:
            action.created_at = datetime.now(timezone.utc).isoformat()
        await session_mgr.persist_night_action(session_id, action, state.round)

        if action.action_type != "none" and action.character_id != "player":
            char = next((c for c in state.characters if c.id == action.character_id), None)
            yield sse.night_action(
                action.character_id, char.name if char else "Unknown",
                action.action_type, action.result,
            )
            await asyncio.sleep(random.uniform(1.0, 2.5))

    # Check if player got an investigation result
    if state.player_investigation_result:
        yield sse.investigation_result(state.player_investigation_result)

    # Check if player was killed at night
    player_killed = state.player_killed_at_night

    # Emit night results with narration and eliminated character IDs
    eliminated_ids = list(dict.fromkeys(
        a.target_id for a in state.night_actions if a.result == "killed" and a.target_id
    ))
    yield sse.night_results(narration_text, eliminated_ids)

    # Emit night_kill_reveal for each killed NPC so frontend can show CharacterReveal
    for killed_id in eliminated_ids:
        if killed_id == "player":
            continue
        char = next((c for c in state.characters if c.id == killed_id), None)
        if char:
            await asyncio.sleep(3)  # Let dawn narration TTS play first
            yield sse.night_kill_reveal({
                "character_id": char.id,
                "character_name": char.name,
                "hidden_role": char.hidden_role,
                "faction": char.faction,
                "win_condition": char.win_condition,
                "hidden_knowledge": char.hidden_knowledge,
                "behavioral_rules": char.behavioral_rules,
                "persona": char.persona,
                "public_role": char.public_role,
                "avatar_seed": char.avatar_seed,
                "voice_id": getattr(char, 'voice_id', ''),
                "is_eliminated": True,
            })

            # Generate and emit last words for the night kill victim
            killed_agent = agents.get(killed_id)
            if killed_agent:
                last_words_text = await killed_agent.generate_last_words("night_kill")
                if last_words_text:
                    yield sse.last_words(char.id, char.name, last_words_text)

    # If player was killed, emit player_eliminated with all hidden info for ghost mode
    if player_killed and state.player_role:
        all_characters = [
            {
                "id": c.id, "name": c.name, "hidden_role": c.hidden_role,
                "faction": c.faction, "is_eliminated": c.is_eliminated,
                "persona": c.persona, "public_role": c.public_role,
                "avatar_seed": c.avatar_seed,
            }
            for c in state.characters
        ]
        yield sse.player_eliminated(
            state.player_role.hidden_role, state.player_role.faction,
            "night_kill", all_characters,
        )

    # Update emotions for night eliminations
    for killed_id in eliminated_ids:
        if killed_id == "player":
            continue
        killed_char = next((c for c in state.characters if c.id == killed_id), None)
        if killed_char:
            for char in game_state.get_alive_characters(state):
                agent = agents.get(char.id)
                if agent:
                    agent.update_emotions_for_elimination(killed_id, killed_char.faction)

    # Record night kills as canon facts
    for killed_id in eliminated_ids:
        if killed_id == "player":
            state.canon_facts.append(
                f"The player (Council Member) was killed during night of round {state.round}"
            )
        else:
            killed_char = next((c for c in state.characters if c.id == killed_id), None)
            if killed_char:
                state.canon_facts.append(
                    f"{killed_char.name} was killed during night of round {state.round} "
                    f"(was {killed_char.hidden_role} of {killed_char.faction})"
                )
    # Push updated canon facts to all alive agents
    for char in game_state.get_alive_characters(state):
        agent = agents.get(char.id)
        if agent:
            agent.update_canon_facts(state.canon_facts)

    # Decay emotions at round boundary for all alive characters
    for char in game_state.get_alive_characters(state):
        agent = agents.get(char.id)
        if agent:
            agent.decay_emotions()

    # Update tension after night results
    state = session_mgr.game_master.update_tension(state)

    # Check win conditions after night
    winner = session_mgr.game_master._check_win_conditions(state)
    if winner:
        state = game_state.end_game(state, winner)
        evil_factions = {
            f.get("name", "")
            for f in state.world.factions
            if f.get("alignment", "").lower() == "evil"
        }
        template_key = "game_end_evil" if winner in evil_factions else "game_end_good"
        end_narration = await session_mgr.game_master._generate_narration(
            state, template_key, {"faction": winner},
        )
        all_characters = [
            {"id": c.id, "name": c.name, "hidden_role": c.hidden_role, "faction": c.faction,
             "is_eliminated": c.is_eliminated, "persona": c.persona, "public_role": c.public_role,
             "avatar_seed": c.avatar_seed}
            for c in state.characters
        ]
        yield sse.game_over(state.winner, end_narration, all_characters)
    else:
        # Advance to next discussion round
        state, disc_narration = await session_mgr.game_master.advance_phase(state, agents)
        if disc_narration:
            yield sse.narration(disc_narration, phase=state.phase, round=state.round)

    session_mgr.store_session(session_id, state)
    await session_mgr.save_session(session_id)
    yield sse.done(phase=state.phase, round=state.round)
