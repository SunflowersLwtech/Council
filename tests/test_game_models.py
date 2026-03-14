"""Tests for Pydantic game models — coercion, validation, edge cases.

Validates that LLM output variations are handled gracefully by model validators,
following the resilient parsing pattern used throughout COUNCIL.
"""

import json
import pytest
from backend.models.game_models import (
    WorldModel, Character, EmotionalState, SimsTraits,
    MindMirror, MindMirrorPlane, GameState, ChatMessage,
    VoteRecord, NightAction, PlayerRole, CharacterPublicInfo,
    GameCreateResponse, GameChatRequest, GameVoteRequest,
    VoteResult, GameEvent, Relationship, Memory,
)


# ── WorldModel Coercion ─────────────────────────────────────────────


class TestWorldModelCoercion:
    """LLMs return inconsistent types — WorldModel must handle them all."""

    def test_none_fields_default_to_empty(self):
        w = WorldModel(title=None, setting=None, flavor_text=None)
        assert w.title == ""
        assert w.setting == ""
        assert w.flavor_text == ""

    def test_dict_coerced_to_json_string(self):
        w = WorldModel(title={"name": "Test"})
        assert '"name"' in w.title

    def test_list_coerced_to_semicolon_string(self):
        w = WorldModel(setting=["dark", "foggy", "medieval"])
        assert "dark; foggy; medieval" == w.setting

    def test_factions_as_string_json(self):
        w = WorldModel(factions='[{"name": "Good"}, {"name": "Evil"}]')
        assert len(w.factions) == 2
        assert w.factions[0]["name"] == "Good"

    def test_factions_as_dict_mapping(self):
        """LLM sometimes returns {name: description} instead of [...]."""
        w = WorldModel(factions={"Village": "the good guys", "Wolves": "the bad guys"})
        assert len(w.factions) == 2
        names = {f["name"] for f in w.factions}
        assert "Village" in names
        assert "Wolves" in names

    def test_factions_none_defaults_empty(self):
        w = WorldModel(factions=None)
        assert w.factions == []

    def test_factions_as_string_list(self):
        w = WorldModel(factions=["Good", "Evil"])
        assert len(w.factions) == 2
        assert w.factions[0] == {"name": "Good"}

    def test_player_count_clamped_to_range(self):
        assert WorldModel(recommended_player_count=3).recommended_player_count == 5
        assert WorldModel(recommended_player_count=20).recommended_player_count == 8
        assert WorldModel(recommended_player_count=7).recommended_player_count == 7

    def test_player_count_invalid_type(self):
        assert WorldModel(recommended_player_count="not_a_number").recommended_player_count == 7

    def test_roles_as_mixed_list(self):
        w = WorldModel(roles=[{"name": "Seer"}, "Villager", 42])
        assert len(w.roles) == 3
        assert w.roles[0] == {"name": "Seer"}
        assert w.roles[1] == {"name": "Villager"}
        assert w.roles[2] == {"name": "42"}


# ── Character Coercion ──────────────────────────────────────────────


class TestCharacterCoercion:

    def test_none_strings_default_empty(self):
        c = Character(name=None, persona=None, faction=None)
        assert c.name == ""
        assert c.persona == ""
        assert c.faction == ""

    def test_hidden_knowledge_from_string(self):
        c = Character(hidden_knowledge="knows the secret")
        assert c.hidden_knowledge == ["knows the secret"]

    def test_hidden_knowledge_from_dict(self):
        c = Character(hidden_knowledge={"fact1": "value1", "fact2": "value2"})
        assert len(c.hidden_knowledge) == 2

    def test_id_auto_generated(self):
        c1 = Character()
        c2 = Character()
        assert c1.id != c2.id
        assert len(c1.id) == 8

    def test_default_emotional_state(self):
        c = Character()
        assert c.emotional_state.happiness == 0.5
        assert c.emotional_state.anger == 0.0

    def test_default_sims_traits(self):
        c = Character()
        assert c.sims_traits.neat == 5
        assert c.sims_traits.outgoing == 5

    def test_moral_values_none(self):
        c = Character(moral_values=None)
        assert c.moral_values == []


# ── EmotionalState ──────────────────────────────────────────────────


class TestEmotionalState:

    def test_default_values(self):
        e = EmotionalState()
        assert e.happiness == 0.5
        assert e.anger == 0.0
        assert e.fear == 0.1
        assert e.trust == 0.5
        assert e.energy == 0.8
        assert e.curiosity == 0.5

    def test_custom_values(self):
        e = EmotionalState(anger=0.9, fear=0.7)
        assert e.anger == 0.9
        assert e.fear == 0.7


# ── ChatMessage ─────────────────────────────────────────────────────


class TestChatMessage:

    def test_none_coercion(self):
        m = ChatMessage(speaker_id=None, content=None)
        assert m.speaker_id == ""
        assert m.content == ""

    def test_defaults(self):
        m = ChatMessage()
        assert m.is_public is True
        assert m.round == 0


# ── VoteRecord ──────────────────────────────────────────────────────


class TestVoteRecord:

    def test_none_coercion(self):
        v = VoteRecord(voter_id=None, target_name=None)
        assert v.voter_id == ""
        assert v.target_name == ""


# ── GameState ───────────────────────────────────────────────────────


class TestGameState:

    def test_default_phase_is_lobby(self):
        s = GameState()
        assert s.phase == "lobby"
        assert s.round == 1
        assert s.winner is None

    def test_session_id_auto_generated(self):
        s1 = GameState()
        s2 = GameState()
        assert s1.session_id != s2.session_id

    def test_characters_default_empty(self):
        s = GameState()
        assert s.characters == []
        assert s.eliminated == []
        assert s.messages == []

    def test_tension_initial(self):
        s = GameState()
        assert s.tension_level == 0.3


# ── CharacterPublicInfo ─────────────────────────────────────────────


class TestCharacterPublicInfo:

    def test_strips_hidden_fields(self, village_elder):
        pub = CharacterPublicInfo(
            id=village_elder.id,
            name=village_elder.name,
            persona=village_elder.persona,
            public_role=village_elder.public_role,
        )
        assert pub.name == "Elder Marcus"
        assert pub.public_role == "Council Elder"
        assert not hasattr(pub, "hidden_role")
        assert not hasattr(pub, "faction")


# ── NightAction ─────────────────────────────────────────────────────


class TestNightAction:

    def test_coercion(self):
        na = NightAction(character_id=None, action_type=None)
        assert na.character_id == ""
        assert na.action_type == ""

    def test_valid_action(self):
        na = NightAction(character_id="wolf01", action_type="kill", target_id="vil01")
        assert na.action_type == "kill"
        assert na.target_id == "vil01"


# ── PlayerRole ──────────────────────────────────────────────────────


class TestPlayerRole:

    def test_defaults(self):
        pr = PlayerRole()
        assert pr.is_eliminated is False
        assert pr.allies == []
        assert pr.potion_stock == {}

    def test_witch_potions(self):
        pr = PlayerRole(
            hidden_role="Witch",
            faction="Village",
            potion_stock={"save": 1, "poison": 1},
        )
        assert pr.potion_stock["save"] == 1
        assert pr.potion_stock["poison"] == 1


# ── MindMirror ──────────────────────────────────────────────────────


class TestMindMirror:

    def test_default_planes(self):
        mm = MindMirror()
        assert mm.bio_energy.traits == {}
        assert mm.emotional.jazz == {}

    def test_none_coercion_in_plane(self):
        plane = MindMirrorPlane(traits=None, jazz=None)
        assert plane.traits == {}
        assert plane.jazz == {}


# ── GameCreateResponse ──────────────────────────────────────────────


class TestGameCreateResponse:

    def test_defaults(self):
        r = GameCreateResponse()
        assert r.session_id == ""
        assert r.phase == "lobby"
        assert r.characters == []


# ── Relationship / Memory ───────────────────────────────────────────


class TestRelationshipAndMemory:

    def test_relationship_defaults(self):
        r = Relationship()
        assert r.closeness == 0.0
        assert r.trust == 0.5

    def test_memory_defaults(self):
        m = Memory()
        assert m.event == ""
        assert m.mood_effect == {}
        assert m.round == 0
