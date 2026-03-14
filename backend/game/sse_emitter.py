"""SSE event serialization helpers for COUNCIL game streaming."""

import json


def _sse(data: dict) -> str:
    """Wrap a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


def error(msg: str, *, character_id: str | None = None) -> str:
    d: dict = {"type": "error", "error": msg}
    if character_id:
        d["character_id"] = character_id
    return _sse(d)


def done(*, tension: float | None = None, phase: str | None = None, round: int | None = None) -> str:
    d: dict = {"type": "done"}
    if tension is not None:
        d["tension"] = tension
    if phase is not None:
        d["phase"] = phase
    if round is not None:
        d["round"] = round
    return _sse(d)


def responders(character_ids: list[str]) -> str:
    return _sse({"type": "responders", "character_ids": character_ids})


def ai_thinking(character_id: str, character_name: str, thinking_content: str) -> str:
    return _sse({
        "type": "ai_thinking",
        "character_id": character_id,
        "character_name": character_name,
        "thinking_content": thinking_content,
    })


def thinking(character_id: str, character_name: str) -> str:
    return _sse({"type": "thinking", "character_id": character_id, "character_name": character_name})


def stream_start(character_id: str, character_name: str) -> str:
    return _sse({"type": "stream_start", "character_id": character_id, "character_name": character_name})


def stream_delta(character_id: str, delta: str) -> str:
    return _sse({"type": "stream_delta", "character_id": character_id, "delta": delta})


def stream_end(
    character_id: str, character_name: str, content: str,
    tts_text: str, voice_id: str, emotion: str,
) -> str:
    return _sse({
        "type": "stream_end",
        "character_id": character_id,
        "character_name": character_name,
        "content": content,
        "tts_text": tts_text,
        "voice_id": voice_id,
        "emotion": emotion,
    })


def voting_started() -> str:
    return _sse({"type": "voting_started"})


def vote(voter_name: str, target_name: str) -> str:
    return _sse({"type": "vote", "voter_name": voter_name, "target_name": target_name})


def tally(tally_data: dict, is_tie: bool) -> str:
    return _sse({"type": "tally", "tally": tally_data, "is_tie": is_tie})


def narration(content: str, *, phase: str | None = None, round: int | None = None) -> str:
    d: dict = {"type": "narration", "content": content}
    if phase is not None:
        d["phase"] = phase
    if round is not None:
        d["round"] = round
    return _sse(d)


def elimination(
    character_id: str, character_name: str,
    hidden_role: str, faction: str, narration_text: str,
) -> str:
    return _sse({
        "type": "elimination",
        "character_id": character_id,
        "character_name": character_name,
        "hidden_role": hidden_role,
        "faction": faction,
        "narration": narration_text,
    })


def player_eliminated(
    hidden_role: str, faction: str, eliminated_by: str,
    all_characters: list[dict], narration_text: str = "",
) -> str:
    d: dict = {
        "type": "player_eliminated",
        "hidden_role": hidden_role,
        "faction": faction,
        "eliminated_by": eliminated_by,
        "all_characters": all_characters,
    }
    if narration_text:
        d["narration"] = narration_text
    return _sse(d)


def last_words(character_id: str, character_name: str, content: str) -> str:
    return _sse({
        "type": "last_words",
        "character_id": character_id,
        "character_name": character_name,
        "content": content,
    })


def game_over(winner: str, narration_text: str, all_characters: list[dict]) -> str:
    return _sse({
        "type": "game_over",
        "winner": winner,
        "narration": narration_text,
        "all_characters": all_characters,
    })


def night_started() -> str:
    return _sse({"type": "night_started"})


def night_action(character_id: str, character_name: str, action_type: str, result: str) -> str:
    return _sse({
        "type": "night_action",
        "character_id": character_id,
        "character_name": character_name,
        "action_type": action_type,
        "result": result,
    })


def night_action_prompt(action_type: str, eligible_targets: list[dict], allies: list[dict]) -> str:
    return _sse({
        "type": "night_action_prompt",
        "action_type": action_type,
        "eligible_targets": eligible_targets,
        "allies": allies,
    })


def investigation_result(result: dict) -> str:
    return _sse({"type": "investigation_result", "investigation_result": result})


def night_results(narration_text: str, eliminated_ids: list[str]) -> str:
    return _sse({"type": "night_results", "narration": narration_text, "eliminated_ids": eliminated_ids})


def night_kill_reveal(char_data: dict) -> str:
    d = {"type": "night_kill_reveal"}
    d.update(char_data)
    return _sse(d)


def discussion_warning(content: str) -> str:
    return _sse({"type": "discussion_warning", "content": content})


def discussion_ending(content: str) -> str:
    return _sse({"type": "discussion_ending", "content": content})


def complication(content: str, tension: float) -> str:
    return _sse({"type": "complication", "content": content, "tension": tension})
