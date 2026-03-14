"""Discussion phase handler — opening statements and player chat."""

import random
import asyncio
import logging
from typing import AsyncGenerator

from backend.models.game_models import ChatMessage
from backend.game import state as game_state
from backend.game import sse_emitter as sse
from backend.voice.tts_middleware import inject_emotion_tags

logger = logging.getLogger(__name__)

# Pacing constants
STREAM_DELTA_PACE_SEC = 0.04
INTER_SPEAKER_PACE_SEC = 0.40
BASE_REACTION_PROB = 0.25


async def handle_open_discussion(session_mgr, session_id: str) -> AsyncGenerator[str, None]:
    """Trigger structured opening statements from ALL alive AI characters. Yields SSE events."""
    state = await session_mgr.get_session(session_id)
    agents = session_mgr.get_agents(session_id)

    if state.phase != "discussion":
        yield sse.error("Open discussion only available during discussion phase")
        return

    # Skip if discussion already has character messages this round
    round_character_msgs = [
        m for m in state.messages
        if m.round == state.round and m.speaker_id != "player" and m.speaker_id != "narrator" and m.speaker_id != ""
    ]
    if round_character_msgs:
        yield sse.done(tension=state.tension_level)
        return

    # Determine AI-optimized speaking order for ALL alive characters
    speaking_order = await session_mgr.game_master.determine_speaking_order(state, agents)
    alive_map = {c.id: c for c in game_state.get_alive_characters(state)}
    speakers = [alive_map[cid] for cid in speaking_order if cid in alive_map]

    yield sse.responders([s.id for s in speakers])

    opening_prompt = (
        "The council session has just begun. This is the structured opening round — "
        "each member speaks in turn. Make a brief opening statement (1-3 sentences) to the council. "
        "You might express suspicion, share an observation, set the tone, or probe others. "
        "Reference events from previous rounds if applicable."
    )

    for i, char in enumerate(speakers):
        agent = agents.get(char.id)
        if not agent:
            continue

        # Generate AI inner thought before public response
        inner_thought = await agent.generate_inner_thought(state.messages)
        if inner_thought:
            yield sse.ai_thinking(char.id, char.name, inner_thought)

        yield sse.thinking(char.id, char.name)

        try:
            yield sse.stream_start(char.id, char.name)

            full_response = ""
            try:
                async for chunk in agent.respond_stream(
                    opening_prompt, state.messages,
                    talk_modifier="Keep your opening brief and impactful.",
                ):
                    full_response += chunk
                    for delta in session_mgr.display_chunks(chunk):
                        yield sse.stream_delta(char.id, delta)
                        await asyncio.sleep(STREAM_DELTA_PACE_SEC)
            except Exception:
                if not full_response:
                    full_response = agent._get_fallback_response()

            response = getattr(agent, '_last_response', None) or full_response

            dominant_emotion = agent.get_dominant_emotion()
            ai_msg = ChatMessage(
                speaker_id=char.id,
                speaker_name=char.name,
                content=response,
                is_public=True,
                phase=state.phase,
                round=state.round,
            )
            session_mgr.stamp_message(ai_msg, emotion=dominant_emotion)
            state.messages.append(ai_msg)
            await session_mgr.persist_message(session_id, ai_msg)

            tts_text = inject_emotion_tags(response, char.emotional_state)
            yield sse.stream_end(char.id, char.name, response, tts_text, char.voice_id, dominant_emotion)
        except Exception as e:
            yield sse.error(str(e), character_id=char.id)
        if i < len(speakers) - 1:
            await asyncio.sleep(INTER_SPEAKER_PACE_SEC)

    state = session_mgr.game_master.update_tension(state)
    session_mgr.store_session(session_id, state)
    await session_mgr.save_session(session_id)
    yield sse.done(tension=state.tension_level)


async def handle_chat(
    session_mgr, session_id: str, message: str,
    target_character_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Handle a player chat message. Yields SSE event strings."""
    state = await session_mgr.get_session(session_id)
    agents = session_mgr.get_agents(session_id)

    if state.phase != "discussion":
        yield sse.error("Chat only available during discussion phase")
        return

    # Ghost mode: eliminated player cannot chat
    if state.player_role and state.player_role.is_eliminated:
        yield sse.error("You have been eliminated. Spectating in ghost mode.")
        return

    # Record player message
    player_msg = ChatMessage(
        speaker_id="player",
        speaker_name="You",
        content=message,
        is_public=True,
        phase=state.phase,
        round=state.round,
    )
    session_mgr.stamp_message(player_msg)
    state.messages.append(player_msg)
    await session_mgr.persist_message(session_id, player_msg)

    # Select which characters respond
    responder_ids = await session_mgr.game_master.select_responders(
        state, message, target_character_id, agents
    )

    yield sse.responders(responder_ids)

    # Update emotions on all alive characters (fire-and-forget)
    emotion_tasks = []
    for char in game_state.get_alive_characters(state):
        agent = agents.get(char.id)
        if agent:
            emotion_tasks.append(agent.update_emotions_llm(message, "player"))
    if emotion_tasks:
        session_mgr.fire_and_forget(
            asyncio.gather(*emotion_tasks, return_exceptions=True)
        )

    for i, char_id in enumerate(responder_ids):
        agent = agents.get(char_id)
        if not agent:
            continue

        char = agent.character

        # Generate AI inner thought before public response
        inner_thought = await agent.generate_inner_thought(state.messages)
        if inner_thought:
            yield sse.ai_thinking(char_id, char.name, inner_thought)

        yield sse.thinking(char_id, char.name)

        try:
            talk_modifier = session_mgr.game_master._get_talk_modifier(state, char_id)

            # Stream response token-by-token via SSE
            yield sse.stream_start(char_id, char.name)

            full_response = ""
            try:
                async for chunk in agent.respond_stream(
                    message, state.messages, talk_modifier=talk_modifier,
                ):
                    full_response += chunk
                    for delta in session_mgr.display_chunks(chunk):
                        yield sse.stream_delta(char_id, delta)
                        await asyncio.sleep(STREAM_DELTA_PACE_SEC)
            except Exception:
                if not full_response:
                    full_response = agent._get_fallback_response()

            response = getattr(agent, '_last_response', None) or full_response

            dominant_emotion = agent.get_dominant_emotion()
            ai_msg = ChatMessage(
                speaker_id=char_id,
                speaker_name=char.name,
                content=response,
                is_public=True,
                phase=state.phase,
                round=state.round,
            )
            session_mgr.stamp_message(ai_msg, emotion=dominant_emotion)
            state.messages.append(ai_msg)
            await session_mgr.persist_message(session_id, ai_msg)

            # Fire-and-forget emotion updates after AI response
            ai_emotion_tasks = []
            for other_char in game_state.get_alive_characters(state):
                other_agent = agents.get(other_char.id)
                if other_agent and other_char.id != char_id:
                    ai_emotion_tasks.append(other_agent.update_emotions_llm(response, char_id))
            if ai_emotion_tasks:
                session_mgr.fire_and_forget(
                    asyncio.gather(*ai_emotion_tasks, return_exceptions=True)
                )

            # Emit stream_end with complete data for TTS
            tts_text = inject_emotion_tags(response, char.emotional_state)
            yield sse.stream_end(char_id, char.name, response, tts_text, char.voice_id, dominant_emotion)
        except Exception as e:
            yield sse.error(str(e), character_id=char_id)
        if i < len(responder_ids) - 1:
            await asyncio.sleep(INTER_SPEAKER_PACE_SEC)

    # Spontaneous reactions: probability based on emotional state
    if len(state.messages) >= 4:
        alive = game_state.get_alive_characters(state)
        non_responders = [
            c for c in alive
            if c.id not in responder_ids and c.id in agents
        ]
        reactor = None
        reactor_agent = None
        if non_responders:
            reactor = random.choice(non_responders)
            reactor_agent = agents[reactor.id]
            reaction_prob = BASE_REACTION_PROB + (reactor.emotional_state.anger * 0.3)
            if random.random() >= reaction_prob:
                reactor = None
                reactor_agent = None
        if non_responders and reactor_agent:
            try:
                reaction = await reactor_agent.react(state.messages)
                if reaction:
                    # Stream reaction via stream_start/delta/end
                    yield sse.stream_start(reactor.id, reactor.name)
                    words = reaction.split(" ")
                    for wi, word in enumerate(words):
                        chunk = word if wi == 0 else " " + word
                        yield sse.stream_delta(reactor.id, chunk)
                        await asyncio.sleep(STREAM_DELTA_PACE_SEC)
                    reactor_emotion = reactor_agent.get_dominant_emotion()
                    react_msg = ChatMessage(
                        speaker_id=reactor.id,
                        speaker_name=reactor.name,
                        content=reaction,
                        is_public=True,
                        phase=state.phase,
                        round=state.round,
                    )
                    session_mgr.stamp_message(react_msg, emotion=reactor_emotion)
                    state.messages.append(react_msg)
                    await session_mgr.persist_message(session_id, react_msg)
                    tts_reaction = inject_emotion_tags(reaction, reactor.emotional_state)
                    yield sse.stream_end(
                        reactor.id, reactor.name, reaction,
                        tts_reaction, reactor.voice_id, reactor_emotion,
                    )
            except Exception:
                pass

    # Update tension level
    state = session_mgr.game_master.update_tension(state)

    # Check discussion turn limits
    limit_status = session_mgr.game_master.check_discussion_limit(state)
    if limit_status == "warning":
        yield sse.discussion_warning("The council grows restless. A vote will be called shortly.")
    elif limit_status == "end":
        yield sse.discussion_ending("The council has heard enough. The vote will now begin.")

    # Complication injection: when discussion stalls, inject a dramatic event
    if session_mgr.game_master.should_inject_complication(state):
        try:
            state, comp_narration = await session_mgr.game_master.inject_complication(state)
            if comp_narration:
                yield sse.complication(comp_narration, state.tension_level)
        except Exception as e:
            logger.warning("Complication injection failed: %s", e)

    session_mgr.store_session(session_id, state)
    await session_mgr.save_session(session_id)
    yield sse.done(tension=state.tension_level)
