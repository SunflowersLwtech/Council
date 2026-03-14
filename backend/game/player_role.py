"""Player role assignment and night action logic — pure functions."""

import random

from backend.models.game_models import PlayerRole, GameState
from backend.game.game_master import EARLY_ROUND_THRESHOLD
from backend.game import state as game_state


def assign_player_role(state: GameState, world, characters) -> PlayerRole:
    """Assign the player a hidden role from the world's role pool."""
    evil_factions = {
        f.get("name", "")
        for f in world.factions
        if f.get("alignment", "").lower() == "evil"
    }
    good_factions = {
        f.get("name", "")
        for f in world.factions
        if f.get("alignment", "").lower() in ("good", "neutral")
    }

    # Count existing faction distribution
    evil_count = sum(1 for c in characters if c.faction in evil_factions)
    good_count = sum(1 for c in characters if c.faction in good_factions)
    total = evil_count + good_count + 1  # +1 for player

    # Target ~1/3 evil. If evil is under-represented, higher chance for player
    target_evil = max(1, total // 3)
    if evil_count < target_evil:
        player_is_evil = random.random() < 0.6
    else:
        player_is_evil = random.random() < 0.15

    # Pick faction
    if player_is_evil and evil_factions:
        player_faction = random.choice(list(evil_factions))
    elif good_factions:
        player_faction = random.choice(list(good_factions))
    else:
        player_faction = evil_factions.pop() if evil_factions else "Unknown"

    # Pick a role from world.roles matching the faction
    matching_roles = [
        r for r in world.roles
        if r.get("faction", r.get("alignment", "")).lower() == player_faction.lower()
        or (player_is_evil and r.get("alignment", "").lower() == "evil")
        or (not player_is_evil and r.get("alignment", "").lower() in ("good", "neutral"))
    ]
    if matching_roles:
        role_info = random.choice(matching_roles)
        role_name = role_info.get("name", "Villager")
    else:
        # Fallback: assign based on faction
        if player_is_evil:
            role_name = "Werewolf"
        else:
            role_options = ["Villager", "Seer", "Doctor"]
            # Avoid duplicate special roles
            existing_roles = {c.hidden_role.lower() for c in characters}
            available = [r for r in role_options if r.lower() not in existing_roles]
            role_name = random.choice(available) if available else "Villager"

    # Find win condition
    win_conditions = {
        wc.get("faction", wc.get("name", "")): wc.get("condition", wc.get("description", ""))
        for wc in world.win_conditions
    }
    win_condition = win_conditions.get(player_faction, "Survive and help your faction win")

    # If player is evil, populate allies
    allies = []
    if player_is_evil:
        allies = [c.id for c in characters if c.faction in evil_factions]

    return PlayerRole(
        hidden_role=role_name,
        faction=player_faction,
        win_condition=win_condition,
        allies=allies,
    )


def get_player_night_action_type(state: GameState) -> str | None:
    """Determine what night action the player can perform, or None."""
    if not state.player_role or state.player_role.is_eliminated:
        return None
    role = state.player_role.hidden_role.lower()
    is_early_round = state.round < EARLY_ROUND_THRESHOLD
    evil_factions = {
        f.get("name", "")
        for f in state.world.factions
        if f.get("alignment", "").lower() == "evil"
    }
    if state.player_role.faction in evil_factions:
        return None if is_early_round else "kill"
    if "seer" in role or "investigat" in role:
        return "investigate"  # Seer can always investigate
    if "doctor" in role or "protect" in role:
        return "protect"
    if "witch" in role or "alchemist" in role:
        stock = state.player_role.potion_stock or {}
        has_save = stock.get("save", 0) > 0
        has_poison = stock.get("poison", 0) > 0
        if has_save:
            return "save"  # Prioritize save; frontend will show both options
        if has_poison:
            return "poison"
        return None  # No potions left
    return None  # Villager — no night action


def get_eligible_night_targets(state: GameState) -> list[dict]:
    """Get list of characters the player can target at night."""
    alive = game_state.get_alive_characters(state)
    action_type = get_player_night_action_type(state)
    targets = []
    for c in alive:
        # Evil players should not target evil allies
        if action_type == "kill" and state.player_role:
            if c.id in state.player_role.allies:
                continue
        targets.append({
            "id": c.id,
            "name": c.name,
            "persona": c.persona,
            "public_role": c.public_role,
            "avatar_seed": c.avatar_seed,
        })
    return targets
