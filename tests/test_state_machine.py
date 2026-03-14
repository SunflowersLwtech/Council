"""Tests for the game phase state machine.

Validates all valid/invalid transitions, round incrementing,
character elimination, and win-condition edge cases.
"""

import pytest
from backend.models.game_models import GameState, Character, WorldModel, PlayerRole
from backend.game.state import (
    validate_transition, transition, InvalidTransition,
    advance_to_discussion, advance_to_night, advance_to_voting,
    advance_to_reveal, end_game, eliminate_character, get_alive_characters,
    TRANSITIONS,
)


# ── Transition Table ────────────────────────────────────────────────


class TestTransitionTable:
    """Verify the state transition matrix."""

    def test_lobby_can_go_to_discussion(self):
        assert validate_transition("lobby", "discussion") is True

    def test_lobby_cannot_go_to_voting(self):
        assert validate_transition("lobby", "voting") is False

    def test_discussion_goes_to_voting(self):
        assert validate_transition("discussion", "voting") is True

    def test_voting_goes_to_reveal(self):
        assert validate_transition("voting", "reveal") is True

    def test_reveal_can_go_to_night_or_ended(self):
        assert validate_transition("reveal", "night") is True
        assert validate_transition("reveal", "ended") is True

    def test_night_goes_to_discussion(self):
        assert validate_transition("night", "discussion") is True

    def test_ended_goes_nowhere(self):
        assert validate_transition("ended", "discussion") is False
        assert validate_transition("ended", "lobby") is False

    def test_unknown_phase_returns_false(self):
        assert validate_transition("unknown", "discussion") is False

    def test_all_valid_transitions_covered(self):
        """Ensure every phase has an entry in TRANSITIONS."""
        expected_phases = {"lobby", "discussion", "voting", "reveal", "night", "ended"}
        assert set(TRANSITIONS.keys()) == expected_phases


# ── transition() Function ───────────────────────────────────────────


class TestTransitionFunction:

    def test_valid_transition_updates_phase(self, lobby_state):
        result = transition(lobby_state, "discussion")
        assert result.phase == "discussion"

    def test_invalid_transition_raises(self, lobby_state):
        with pytest.raises(InvalidTransition, match="Cannot transition"):
            transition(lobby_state, "voting")

    def test_discussion_from_night_increments_round(self, night_state):
        assert night_state.round == 1
        result = transition(night_state, "discussion")
        assert result.phase == "discussion"
        assert result.round == 2

    def test_discussion_from_lobby_does_not_increment(self, lobby_state):
        result = transition(lobby_state, "discussion")
        assert result.round == 1


# ── Convenience Transition Functions ────────────────────────────────


class TestAdvanceFunctions:

    def test_advance_to_discussion_from_lobby(self, lobby_state):
        result = advance_to_discussion(lobby_state)
        assert result.phase == "discussion"
        assert result.round == 1
        assert result.votes == []

    def test_advance_to_discussion_from_night(self, night_state):
        result = advance_to_discussion(night_state)
        assert result.phase == "discussion"
        assert result.round == 2
        assert result.votes == []

    def test_advance_to_discussion_from_invalid_raises(self, voting_state):
        with pytest.raises(InvalidTransition):
            advance_to_discussion(voting_state)

    def test_advance_to_voting(self, discussion_state):
        result = advance_to_voting(discussion_state)
        assert result.phase == "voting"
        assert result.votes == []

    def test_advance_to_voting_from_invalid(self, lobby_state):
        with pytest.raises(InvalidTransition):
            advance_to_voting(lobby_state)

    def test_advance_to_reveal(self, voting_state):
        result = advance_to_reveal(voting_state)
        assert result.phase == "reveal"

    def test_advance_to_reveal_from_invalid(self, discussion_state):
        with pytest.raises(InvalidTransition):
            advance_to_reveal(discussion_state)

    def test_advance_to_night(self, default_world, five_characters):
        state = GameState(phase="reveal", world=default_world, characters=five_characters)
        result = advance_to_night(state)
        assert result.phase == "night"
        assert result.night_actions == []

    def test_advance_to_night_from_invalid(self, discussion_state):
        with pytest.raises(InvalidTransition):
            advance_to_night(discussion_state)


# ── End Game ────────────────────────────────────────────────────────


class TestEndGame:

    def test_end_game_sets_winner(self, discussion_state):
        result = end_game(discussion_state, "Village")
        assert result.phase == "ended"
        assert result.winner == "Village"

    def test_end_game_wolf_win(self, discussion_state):
        result = end_game(discussion_state, "Wolves")
        assert result.winner == "Wolves"


# ── Character Elimination ──────────────────────────────────────────


class TestElimination:

    def test_eliminate_character(self, discussion_state):
        result = eliminate_character(discussion_state, "elder01")
        assert "elder01" in result.eliminated
        elder = next(c for c in result.characters if c.id == "elder01")
        assert elder.is_eliminated is True

    def test_eliminate_same_character_twice(self, discussion_state):
        eliminate_character(discussion_state, "elder01")
        eliminate_character(discussion_state, "elder01")
        assert discussion_state.eliminated.count("elder01") == 1

    def test_eliminate_player(self, discussion_state):
        discussion_state.player_role = PlayerRole(
            hidden_role="Villager", faction="Village",
        )
        result = eliminate_character(discussion_state, "player")
        assert result.player_role.is_eliminated is True
        assert "player" in result.eliminated

    def test_get_alive_characters(self, discussion_state):
        alive = get_alive_characters(discussion_state)
        assert len(alive) == 5

        eliminate_character(discussion_state, "elder01")
        alive = get_alive_characters(discussion_state)
        assert len(alive) == 4
        assert all(c.id != "elder01" for c in alive)

    def test_eliminate_all_wolves(self, discussion_state):
        """Eliminate the only wolf — village should have no wolves left."""
        eliminate_character(discussion_state, "spy01")
        alive = get_alive_characters(discussion_state)
        wolves = [c for c in alive if c.faction == "Wolves"]
        assert len(wolves) == 0


# ── Full Game Lifecycle ─────────────────────────────────────────────


class TestFullLifecycle:
    """Test a complete game flow: lobby → discussion → voting → reveal → night → ... → ended."""

    def test_full_round_cycle(self, lobby_state):
        state = lobby_state

        # Lobby → Discussion
        state = advance_to_discussion(state)
        assert state.phase == "discussion"
        assert state.round == 1

        # Discussion → Voting
        state = advance_to_voting(state)
        assert state.phase == "voting"

        # Voting → Reveal
        state = advance_to_reveal(state)
        assert state.phase == "reveal"

        # Reveal → Night
        state = advance_to_night(state)
        assert state.phase == "night"

        # Night → Discussion (round 2)
        state = advance_to_discussion(state)
        assert state.phase == "discussion"
        assert state.round == 2

        # Discussion → Voting
        state = advance_to_voting(state)
        assert state.phase == "voting"

        # Voting → Reveal
        state = advance_to_reveal(state)
        assert state.phase == "reveal"

        # Game end
        state = end_game(state, "Village")
        assert state.phase == "ended"
        assert state.winner == "Village"
