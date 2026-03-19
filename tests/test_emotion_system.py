"""Tests for the emotion system — personality-modulated reactions, decay, memory creation.

References SightLine's pattern of testing LOD-adaptive behavior:
different personality profiles should produce different emotional responses
to the same game event, similar to how LOD levels produce different scene analyses.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("MISTRAL_API_KEY", "test_key_for_unit_tests")

from backend.models.game_models import (
    WorldModel, Character, SimsTraits, MindMirror, MindMirrorPlane,
    EmotionalState,
)
from backend.game.character_agent import CharacterAgent
from backend.voice.tts_middleware import inject_emotion_tags


# ── Emotion Tag Injection ───────────────────────────────────────────


class TestEmotionTagInjection:
    """Test that emotional states produce correct Gemini-compatible style instructions."""

    def test_angry_tag(self):
        es = EmotionalState(anger=0.8)
        result = inject_emotion_tags("I disagree!", es)
        assert "angrily" in result and "I disagree!" in result

    def test_scared_tag(self):
        es = EmotionalState(fear=0.8)
        result = inject_emotion_tags("What was that?", es)
        assert "fearfully" in result and "What was that?" in result

    def test_excited_tag(self):
        es = EmotionalState(happiness=0.9, energy=0.8)
        result = inject_emotion_tags("We found them!", es)
        assert "excitement" in result and "We found them!" in result

    def test_laughs_tag(self):
        es = EmotionalState(happiness=0.8, energy=0.3)
        result = inject_emotion_tags("How amusing.", es)
        assert "cheerfully" in result and "How amusing." in result

    def test_curious_tag(self):
        es = EmotionalState(curiosity=0.8)
        result = inject_emotion_tags("Tell me more.", es)
        assert "curiosity" in result and "Tell me more." in result

    def test_suspicious_tag(self):
        es = EmotionalState(trust=0.2)
        result = inject_emotion_tags("I don't believe you.", es)
        assert "suspiciously" in result and "I don't believe you." in result

    def test_sighs_tag(self):
        es = EmotionalState(energy=0.1)
        result = inject_emotion_tags("This is exhausting.", es)
        assert "wearily" in result and "This is exhausting." in result

    def test_neutral_no_tag(self):
        es = EmotionalState()
        result = inject_emotion_tags("Let's proceed.", es)
        assert result == "Let's proceed."

    def test_priority_order_anger_first(self):
        """Anger should take precedence over fear when both are high."""
        es = EmotionalState(anger=0.7, fear=0.7)
        result = inject_emotion_tags("Stop!", es)
        assert "angrily" in result

    def test_priority_fear_over_happiness(self):
        """Fear beats happiness when anger is low."""
        es = EmotionalState(anger=0.1, fear=0.8, happiness=0.9, energy=0.9)
        result = inject_emotion_tags("Oh no!", es)
        assert "fearfully" in result


# ── Personality-Modulated Emotion Updates ───────────────────────────


class TestPersonalityModulatedEmotions:
    """Test that personality traits modulate emotional responses.

    Same pattern as SightLine's LOD engine tests: different contexts
    should produce different behavior from the same stimulus.
    """

    @pytest.fixture
    def confident_agent(self, minimal_world):
        char = Character(
            id="conf", name="Confident", faction="Village", hidden_role="Villager",
            sims_traits=SimsTraits(neat=5, outgoing=5, active=5, playful=5, nice=5),
            mind_mirror=MindMirror(
                emotional=MindMirrorPlane(traits={"confident": 7}, jazz={}),
            ),
        )
        return CharacterAgent(char, minimal_world)

    @pytest.fixture
    def timid_agent(self, minimal_world):
        char = Character(
            id="timid", name="Timid", faction="Village", hidden_role="Villager",
            sims_traits=SimsTraits(neat=5, outgoing=2, active=3, playful=2, nice=8),
            mind_mirror=MindMirror(
                emotional=MindMirrorPlane(traits={"confident": 1}, jazz={}),
            ),
        )
        return CharacterAgent(char, minimal_world)

    @pytest.fixture
    def forceful_agent(self, minimal_world):
        char = Character(
            id="force", name="Forceful", faction="Village", hidden_role="Villager",
            sims_traits=SimsTraits(neat=5, outgoing=7, active=8, playful=3, nice=3),
            mind_mirror=MindMirror(
                emotional=MindMirrorPlane(traits={"forceful": 7}, jazz={}),
            ),
        )
        return CharacterAgent(char, minimal_world)

    def test_confident_less_fear_on_accusation(self, confident_agent, timid_agent):
        """Confident character should gain less fear from accusation."""
        conf_fear_before = confident_agent.character.emotional_state.fear
        timid_fear_before = timid_agent.character.emotional_state.fear

        confident_agent.update_emotions("I suspect Confident is the traitor!", "accuser")
        timid_agent.update_emotions("I suspect Timid is the traitor!", "accuser")

        conf_delta = confident_agent.character.emotional_state.fear - conf_fear_before
        timid_delta = timid_agent.character.emotional_state.fear - timid_fear_before

        assert conf_delta < timid_delta, (
            f"Confident fear delta ({conf_delta:.3f}) should be less than "
            f"timid fear delta ({timid_delta:.3f})"
        )

    def test_forceful_converts_fear_to_anger(self, forceful_agent):
        """Forceful character should respond to accusation with more anger."""
        anger_before = forceful_agent.character.emotional_state.anger
        forceful_agent.update_emotions("I suspect Forceful is a lying traitor!", "accuser")
        anger_after = forceful_agent.character.emotional_state.anger

        assert anger_after > anger_before + 0.05, (
            f"Forceful anger should increase: {anger_before:.3f} → {anger_after:.3f}"
        )

    def test_emotion_decay(self, forceful_agent):
        """Emotions should decay toward baseline over time."""
        forceful_agent.update_emotions("I suspect Forceful is a lying traitor!", "accuser")
        anger_peak = forceful_agent.character.emotional_state.anger

        forceful_agent.decay_emotions()
        anger_decayed = forceful_agent.character.emotional_state.anger

        assert anger_decayed < anger_peak, (
            f"Anger should decay: {anger_peak:.3f} → {anger_decayed:.3f}"
        )

    def test_support_increases_trust(self, timid_agent):
        """Supportive message should increase trust."""
        trust_before = timid_agent.character.emotional_state.trust
        timid_agent.update_emotions("I believe Timid is innocent and honest.", "supporter")
        trust_after = timid_agent.character.emotional_state.trust

        assert trust_after >= trust_before, (
            f"Trust should not decrease on support: {trust_before:.3f} → {trust_after:.3f}"
        )

    def test_memory_created_on_accusation(self, forceful_agent):
        """Accusation should create a memory entry."""
        initial_memories = len(forceful_agent.character.recent_memories)
        forceful_agent.update_emotions("You are the werewolf, Forceful! I accuse you!", "accuser")
        assert len(forceful_agent.character.recent_memories) > initial_memories


# ── Relationship Updates ────────────────────────────────────────────


class TestRelationshipUpdates:
    """Test that emotional events affect character relationships."""

    def test_accusation_lowers_trust_in_accuser(self, minimal_world):
        char = Character(
            id="r1", name="TestChar", faction="Village", hidden_role="Villager",
            relationships=[],
        )
        agent = CharacterAgent(char, minimal_world)
        agent.update_emotions("I suspect TestChar is the traitor!", "accuser01")

        # Check if relationship was created or updated
        accuser_rels = [r for r in char.relationships if r.target_id == "accuser01"]
        if accuser_rels:
            assert accuser_rels[0].trust < 0.5, "Trust should decrease toward accuser"
