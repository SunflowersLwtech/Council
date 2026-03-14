"""Voting phase handler."""

from typing import AsyncGenerator

from backend.game import state as game_state
from backend.game import sse_emitter as sse


async def handle_vote(
    session_mgr, session_id: str, target_character_id: str,
) -> AsyncGenerator[str, None]:
    """Handle player vote. Yields SSE events for voting flow."""
    state = await session_mgr.get_session(session_id)
    agents = session_mgr.get_agents(session_id)

    # Transition to voting if still in discussion
    if state.phase == "discussion":
        state, narr = await session_mgr.game_master.advance_phase(state, agents)
        if narr:
            yield sse.narration(narr)

    if state.phase != "voting":
        yield sse.error("Not in voting phase")
        return

    yield sse.voting_started()

    # Process votes
    state, vote_result = await session_mgr.game_master.handle_voting(
        state, target_character_id, agents
    )

    # Persist and emit each vote
    for v in vote_result.votes:
        await session_mgr.persist_vote(session_id, v, state.round)
        yield sse.vote(v.voter_name, v.target_name)

    # Emit tally
    yield sse.tally(vote_result.tally, vote_result.is_tie)

    # Transition to reveal
    state, _ = await session_mgr.game_master.advance_phase(state, agents)

    if vote_result.is_tie:
        # Use Master Agent ruling narration if available, else fallback
        if vote_result.ruling_narration:
            narr_text = vote_result.ruling_narration
        else:
            narr_text = await session_mgr.game_master._generate_narration(state, "tie_vote", {})
        yield sse.narration(narr_text)
    elif vote_result.eliminated_id:
        # Check if the player was eliminated
        if vote_result.eliminated_id == "player" and state.player_role:
            state.player_role.eliminated_by = "vote"
            state.canon_facts.append(
                f"The player (Council Member) was eliminated in round {state.round} by vote"
            )

            # Emit player_eliminated with all hidden info for ghost mode
            all_characters = [
                {
                    "id": c.id, "name": c.name, "hidden_role": c.hidden_role,
                    "faction": c.faction, "is_eliminated": c.is_eliminated,
                    "persona": c.persona, "public_role": c.public_role,
                    "avatar_seed": c.avatar_seed,
                }
                for c in state.characters
            ]
            narr_text = await session_mgr.game_master._generate_narration(
                state, "elimination", {
                    "name": "You (Council Member)",
                    "role": state.player_role.hidden_role,
                    "faction": state.player_role.faction,
                }
            )
            yield sse.player_eliminated(
                state.player_role.hidden_role, state.player_role.faction,
                "vote", all_characters, narr_text,
            )
            yield sse.elimination(
                "player", "You",
                state.player_role.hidden_role, state.player_role.faction,
                narr_text,
            )
        else:
            eliminated_char = next(
                (c for c in state.characters if c.id == vote_result.eliminated_id), None
            )
            if eliminated_char:
                # Record elimination as canon
                state.canon_facts.append(
                    f"{eliminated_char.name} was eliminated in round {state.round} "
                    f"(was {eliminated_char.hidden_role} of {eliminated_char.faction})"
                )

                # Push updated canon facts to all alive agents
                for char in game_state.get_alive_characters(state):
                    agent = agents.get(char.id)
                    if agent:
                        agent.update_canon_facts(state.canon_facts)

                # Update emotions on all alive characters after elimination
                for char in game_state.get_alive_characters(state):
                    agent = agents.get(char.id)
                    if agent:
                        agent.update_emotions_for_elimination(
                            vote_result.eliminated_id, eliminated_char.faction
                        )

                narr_text = await session_mgr.game_master._generate_narration(
                    state, "elimination", {
                        "name": eliminated_char.name,
                        "role": eliminated_char.hidden_role,
                        "faction": eliminated_char.faction,
                    }
                )
                yield sse.elimination(
                    vote_result.eliminated_id, vote_result.eliminated_name,
                    eliminated_char.hidden_role, eliminated_char.faction,
                    narr_text,
                )

                # Generate and emit last words from the eliminated character
                eliminated_agent = agents.get(vote_result.eliminated_id)
                if eliminated_agent:
                    last_words_text = await eliminated_agent.generate_last_words("vote")
                    if last_words_text:
                        yield sse.last_words(
                            vote_result.eliminated_id,
                            vote_result.eliminated_name,
                            last_words_text,
                        )

    # Check win condition and advance (reveal -> night or ended)
    state, narr_text = await session_mgr.game_master.advance_phase(state, agents)
    if state.phase == "ended":
        all_characters = [
            {"id": c.id, "name": c.name, "hidden_role": c.hidden_role, "faction": c.faction,
             "is_eliminated": c.is_eliminated, "persona": c.persona, "public_role": c.public_role,
             "avatar_seed": c.avatar_seed}
            for c in state.characters
        ]
        yield sse.game_over(state.winner, narr_text, all_characters)
    elif state.phase == "night":
        # Emit night start narration
        if narr_text:
            yield sse.narration(narr_text, phase=state.phase, round=state.round)

        # Summarize round for all agents before night
        alive = game_state.get_alive_characters(state)
        round_msgs = [m for m in state.messages if m.round == state.round]
        for char in alive:
            agent = agents.get(char.id)
            if agent:
                try:
                    await agent.summarize_round(round_msgs)
                except Exception:
                    pass

        session_mgr.store_session(session_id, state)
        await session_mgr.save_session(session_id)

        # Night phase is now triggered separately by the frontend
    else:
        if narr_text:
            yield sse.narration(narr_text, phase=state.phase, round=state.round)

    session_mgr.store_session(session_id, state)
    await session_mgr.save_session(session_id)
    yield sse.done(phase=state.phase, round=state.round)
