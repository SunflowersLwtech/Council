"""Shared pytest fixtures for COUNCIL game tests.

Provides reusable characters, world models, game states, and emotional states
following the same pattern as SightLine's conftest.py.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure a dummy MISTRAL_API_KEY for tests that don't hit the real API
os.environ.setdefault("MISTRAL_API_KEY", "test_key_for_unit_tests")

from backend.models.game_models import (
    WorldModel, Character, EmotionalState, SimsTraits,
    MindMirror, MindMirrorPlane, GameState, ChatMessage,
    VoteRecord, NightAction, PlayerRole, Relationship, Memory,
    CharacterPublicInfo, GameEvent,
)


# ── World Model Fixtures ────────────────────────────────────────────


@pytest.fixture
def default_world() -> WorldModel:
    """A standard medieval village world for testing."""
    return WorldModel(
        title="Shadowfen Village",
        setting="A fog-shrouded village where whispers carry more weight than swords.",
        factions=[
            {"name": "Village", "alignment": "good", "description": "The innocent townsfolk"},
            {"name": "Wolves", "alignment": "evil", "description": "Werewolves hiding among villagers"},
        ],
        roles=[
            {"name": "Villager", "faction": "Village", "ability": "Vote to eliminate"},
            {"name": "Seer", "faction": "Village", "ability": "Investigate one player per night"},
            {"name": "Doctor", "faction": "Village", "ability": "Protect one player per night"},
            {"name": "Werewolf", "faction": "Wolves", "ability": "Kill one villager per night"},
        ],
        win_conditions=[
            {"faction": "Village", "condition": "Eliminate all werewolves"},
            {"faction": "Wolves", "condition": "Equal or outnumber villagers"},
        ],
        flavor_text="The moon hangs low over Shadowfen...",
        recommended_player_count=7,
    )


@pytest.fixture
def minimal_world() -> WorldModel:
    """Minimal world for unit tests that don't need full setup."""
    return WorldModel(title="Test World", setting="Test setting")


# ── Character Fixtures ──────────────────────────────────────────────


@pytest.fixture
def village_elder(default_world) -> Character:
    """A good-aligned elder character (Village faction)."""
    return Character(
        id="elder01",
        name="Elder Marcus",
        persona="A wise but cautious village leader who has seen many winters.",
        speaking_style="formal and measured, with occasional proverbs",
        avatar_seed="elder_marcus",
        public_role="Council Elder",
        hidden_role="Villager",
        faction="Village",
        win_condition="Eliminate all werewolves",
        hidden_knowledge=["Has seen strange tracks near the mill"],
        behavioral_rules=["Speak with authority", "Reference village history"],
        big_five="O:high, C:high, E:medium, A:high, N:low",
        mbti="INTJ",
        moral_values=["justice", "tradition", "order"],
        decision_making_style="deliberate and principled",
        voice_id="George",
        sims_traits=SimsTraits(neat=7, outgoing=4, active=3, playful=2, nice=6),
        mind_mirror=MindMirror(
            emotional=MindMirrorPlane(
                traits={"confident": 6, "empathic": 4},
                jazz={"confident": "carries weight of years", "empathic": "listens before judging"},
            ),
        ),
        personality_summary="wise and measured, a pillar of the community",
        current_mood="watchful",
        driving_need="protect the village",
        want="uncover the truth",
        method="careful observation and pointed questions",
    )


@pytest.fixture
def werewolf_spy() -> Character:
    """An evil-aligned spy character (Wolves faction)."""
    return Character(
        id="spy01",
        name="Swift Lila",
        persona="A quick-witted trader who arrived in the village last month.",
        speaking_style="casual with sharp observations, deflects with humor",
        avatar_seed="swift_lila",
        public_role="Traveling Trader",
        hidden_role="Werewolf",
        faction="Wolves",
        win_condition="Equal or outnumber villagers",
        hidden_knowledge=["Knows the other wolf is the blacksmith"],
        behavioral_rules=["Deflect suspicion with charm", "Never reveal wolf allies"],
        big_five="O:high, C:low, E:high, A:medium, N:medium",
        mbti="ENTP",
        moral_values=["survival", "cunning", "loyalty to pack"],
        decision_making_style="opportunistic and adaptive",
        voice_id="Sarah",
        sims_traits=SimsTraits(neat=3, outgoing=9, active=7, playful=6, nice=5),
        mind_mirror=MindMirror(
            emotional=MindMirrorPlane(
                traits={"forceful": 5, "confident": 6},
                jazz={"forceful": "pushes agenda subtly", "confident": "rarely shows doubt"},
            ),
        ),
        personality_summary="bold and talkative, hides danger behind charm",
        current_mood="alert",
        driving_need="survive the vote",
        want="protect herself and her wolf ally",
        method="deflection and social manipulation",
    )


@pytest.fixture
def seer_character() -> Character:
    """A Seer character with investigation ability."""
    return Character(
        id="seer01",
        name="Quiet Jasper",
        persona="A hermit who speaks rarely but sees deeply.",
        speaking_style="terse and blunt, uses metaphors",
        avatar_seed="quiet_jasper",
        public_role="Hermit",
        hidden_role="Seer",
        faction="Village",
        win_condition="Eliminate all werewolves",
        hidden_knowledge=["Can investigate one player each night"],
        behavioral_rules=["Reveal information carefully", "Avoid becoming a target"],
        sims_traits=SimsTraits(neat=6, outgoing=1, active=4, playful=2, nice=4),
        personality_summary="withdrawn and watchful",
        current_mood="pensive",
        want="reveal the wolves without being killed",
        method="observation and cryptic hints",
    )


@pytest.fixture
def doctor_character() -> Character:
    """A Doctor character with protection ability."""
    return Character(
        id="doc01",
        name="Healer Mira",
        persona="The village healer, gentle but perceptive.",
        speaking_style="warm and reassuring, occasionally sharp when pressed",
        avatar_seed="healer_mira",
        public_role="Village Healer",
        hidden_role="Doctor",
        faction="Village",
        win_condition="Eliminate all werewolves",
        sims_traits=SimsTraits(neat=8, outgoing=6, active=5, playful=3, nice=9),
        personality_summary="compassionate but steel-willed when lives are at stake",
        want="protect the innocent",
        method="observation and strategic protection",
    )


@pytest.fixture
def five_characters(village_elder, werewolf_spy, seer_character, doctor_character) -> list[Character]:
    """A balanced set of 5 characters for game testing."""
    villager = Character(
        id="vil01", name="Baker Tom", faction="Village",
        hidden_role="Villager", persona="The cheerful baker",
        speaking_style="folksy and warm",
        public_role="Baker",
        sims_traits=SimsTraits(neat=5, outgoing=7, active=4, playful=8, nice=7),
    )
    return [village_elder, werewolf_spy, seer_character, doctor_character, villager]


# ── Emotional State Fixtures ────────────────────────────────────────


@pytest.fixture
def neutral_emotions() -> EmotionalState:
    return EmotionalState()


@pytest.fixture
def angry_emotions() -> EmotionalState:
    return EmotionalState(anger=0.8, happiness=0.1, trust=0.2, energy=0.9)


@pytest.fixture
def scared_emotions() -> EmotionalState:
    return EmotionalState(fear=0.8, happiness=0.1, trust=0.3, energy=0.4)


@pytest.fixture
def excited_emotions() -> EmotionalState:
    return EmotionalState(happiness=0.9, energy=0.8, curiosity=0.7)


# ── Game State Fixtures ─────────────────────────────────────────────


@pytest.fixture
def lobby_state(default_world, five_characters) -> GameState:
    """A game in the lobby phase with characters loaded."""
    return GameState(
        session_id="test-session-001",
        phase="lobby",
        round=1,
        world=default_world,
        characters=five_characters,
        active_skills=[],
    )


@pytest.fixture
def discussion_state(default_world, five_characters) -> GameState:
    """A game in discussion phase with some messages."""
    state = GameState(
        session_id="test-session-002",
        phase="discussion",
        round=1,
        world=default_world,
        characters=five_characters,
        messages=[
            ChatMessage(
                speaker_id="elder01", speaker_name="Elder Marcus",
                content="I sense darkness among us tonight.", round=1,
            ),
            ChatMessage(
                speaker_id="spy01", speaker_name="Swift Lila",
                content="Come now, Elder, don't scare the children.", round=1,
            ),
        ],
    )
    return state


@pytest.fixture
def voting_state(discussion_state) -> GameState:
    """A game in voting phase."""
    discussion_state.phase = "voting"
    return discussion_state


@pytest.fixture
def night_state(default_world, five_characters) -> GameState:
    """A game in night phase."""
    return GameState(
        session_id="test-session-003",
        phase="night",
        round=1,
        world=default_world,
        characters=five_characters,
    )


@pytest.fixture
def late_game_state(default_world, five_characters) -> GameState:
    """A game in round 3 with eliminations and tension."""
    state = GameState(
        session_id="test-session-late",
        phase="discussion",
        round=3,
        world=default_world,
        characters=five_characters,
        eliminated=["vil01"],
        tension_level=0.7,
    )
    state.characters[4].is_eliminated = True  # Baker Tom
    return state


# ── Mock Helpers ────────────────────────────────────────────────────


@pytest.fixture
def mock_mistral():
    """Mock Mistral client that returns configurable responses."""
    with patch("backend.agents.base_agent.Mistral") as MockMistral:
        mock_client = MagicMock()
        MockMistral.return_value = mock_client

        # Default: return a simple in-character response
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "*narrows eyes* I find your question... interesting."
        mock_choice.message.tool_calls = None
        mock_response.choices = [mock_choice]
        mock_client.chat.complete_async = AsyncMock(return_value=mock_response)

        # Stream mock
        async def mock_stream(*args, **kwargs):
            chunks = ["*leans", " forward*", " Tell me", " more."]
            for chunk in chunks:
                event = MagicMock()
                event.data.choices[0].delta.content = chunk
                yield event

        mock_client.chat.stream_async = MagicMock(return_value=mock_stream())

        yield mock_client


@pytest.fixture
def mock_elevenlabs():
    """Mock ElevenLabs client for voice tests.

    Patches 'elevenlabs.ElevenLabs' because VoiceMiddleware imports it
    inside __init__ via 'from elevenlabs import ElevenLabs'.
    """
    mock_client = MagicMock()

    # TTS returns fake MP3 bytes
    mock_client.text_to_speech.convert.return_value = [b"\xff\xfb\x90\x00" * 100]

    # STT returns transcribed text
    mock_stt_result = MagicMock()
    mock_stt_result.text = "I think the elder is suspicious."
    mock_client.speech_to_text.convert.return_value = mock_stt_result

    # Voices list
    mock_voice = MagicMock()
    mock_voice.name = "Sarah"
    mock_voice.voice_id = "voice_sarah_id"
    mock_voices = MagicMock()
    mock_voices.voices = [mock_voice]
    mock_client.voices.get_all.return_value = mock_voices

    # SFX
    mock_client.text_to_sound_effects.convert.return_value = [b"\xff\xfb\x90\x00" * 50]

    with patch("elevenlabs.ElevenLabs", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_persistence():
    """Mock PersistenceManager for tests that don't need Redis/Supabase."""
    with patch("backend.game.persistence.PersistenceManager") as MockPM:
        mock_pm = MagicMock()
        mock_pm.available = False
        mock_pm.connect = AsyncMock()
        mock_pm.close = AsyncMock()
        mock_pm.save_game_state = AsyncMock()
        mock_pm.load_game_state = AsyncMock(return_value=None)
        MockPM.return_value = mock_pm
        yield mock_pm
