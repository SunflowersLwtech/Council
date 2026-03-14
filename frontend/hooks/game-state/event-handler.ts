/**
 * Maps SSE GameStreamEvent to reducer dispatch calls.
 * Replaces the 621-line handleStreamEvent switch statement.
 */

import type { Dispatch, RefObject } from "react";
import type { GameStreamEvent, CharacterRevealed, GameSession } from "@/lib/game-types";
import type { GameAction } from "./types";
import type { StreamBuffer } from "./stream-buffer";
import * as api from "@/lib/api";

type OnCharacterResponse = (content: string, characterName: string, voiceId?: string, characterId?: string) => void;

interface EventHandlerContext {
  dispatch: Dispatch<GameAction>;
  streamBuffer: StreamBuffer;
  sessionRef: RefObject<GameSession | null>;
  revealedCharacterRef: RefObject<CharacterRevealed | null>;
  deferredPhaseRef: { current: { phase: string; round?: number } | null };
  pendingDiscussionEndRef: { current: boolean };
  onCharacterResponseRef: RefObject<OnCharacterResponse | undefined>;
}

function maybeApplyPhase(
  ctx: EventHandlerContext,
  nextPhase?: string,
  nextRound?: number,
) {
  if (!nextPhase) return;
  // If reveal overlay is up, defer reveal->night
  if (nextPhase === "night" && ctx.revealedCharacterRef.current) {
    ctx.deferredPhaseRef.current = { phase: nextPhase, round: nextRound };
    return;
  }
  ctx.dispatch({
    type: "SET_PHASE",
    phase: nextPhase as any,
    round: nextRound,
  });
}

export function createStreamEventHandler(ctx: EventHandlerContext) {
  const { dispatch, streamBuffer } = ctx;

  return function handleStreamEvent(event: GameStreamEvent) {
    switch (event.type) {
      case "responders":
        // List of characters who will respond - no UI action needed
        break;

      case "thinking":
        if (event.character_name) {
          dispatch({
            type: "ADD_THINKING",
            characterId: event.character_id,
            characterName: event.character_name,
          });
        }
        break;

      case "stream_start": {
        const actorKey =
          event.character_id || event.character_name || "__unknown_stream_actor";
        streamBuffer.resetActor(actorKey);
        dispatch({
          type: "STREAM_START",
          characterId: event.character_id,
          characterName: event.character_name,
          actorKey,
        });
        break;
      }

      case "stream_delta":
        streamBuffer.enqueueDelta(event);
        break;

      case "stream_end": {
        const actorKey =
          event.character_id || event.character_name || "__unknown_stream_actor";
        streamBuffer.markEnd(actorKey, event);
        break;
      }

      case "response": {
        // Legacy non-streaming response (fallback)
        const actorKey =
          event.character_id || event.character_name || "__unknown_stream_actor";
        streamBuffer.resetActor(actorKey);
        delete (streamBuffer as any).buffers?.[actorKey];
        dispatch({
          type: "ADD_MESSAGE",
          message: {
            role: "character",
            characterId: event.character_id,
            characterName: event.character_name,
            content: event.content || "",
            voiceId: event.voice_id,
            emotion: event.emotion,
          },
        });
        if (event.content && event.character_name) {
          ctx.onCharacterResponseRef.current?.(
            event.content, event.character_name, event.voice_id, event.character_id,
          );
        }
        break;
      }

      case "reaction": {
        const actorKey =
          event.character_id || event.character_name || "__unknown_stream_actor";
        streamBuffer.resetActor(actorKey);
        dispatch({
          type: "ADD_MESSAGE",
          message: {
            role: "character",
            characterId: event.character_id,
            characterName: event.character_name,
            content: event.content || "",
            voiceId: event.voice_id,
            emotion: event.emotion,
          },
        });
        if (event.content && event.character_name) {
          ctx.onCharacterResponseRef.current?.(
            event.content, event.character_name, event.voice_id, event.character_id,
          );
        }
        break;
      }

      case "complication":
        dispatch({
          type: "COMPLICATION",
          content: event.content || "Something unexpected happens...",
          tension: event.tension,
        });
        if (event.content) {
          ctx.onCharacterResponseRef.current?.(event.content, "Narrator");
        }
        break;

      case "discussion_warning":
        dispatch({
          type: "DISCUSSION_WARNING",
          content: event.content || "The council grows restless. A vote will be called shortly.",
        });
        break;

      case "discussion_ending":
        ctx.pendingDiscussionEndRef.current = false;
        dispatch({
          type: "DISCUSSION_ENDING",
          content: event.content || "The council has heard enough. The vote will now begin.",
        });
        break;

      case "night_action":
        dispatch({ type: "NIGHT_ACTION", characterName: event.character_name });
        break;

      case "narration":
        dispatch({
          type: "NARRATION",
          content: event.content || event.narration || "",
          phase: event.phase,
          round: event.round,
        });
        if (event.content || event.narration) {
          ctx.onCharacterResponseRef.current?.(
            event.content || event.narration || "", "Narrator",
          );
        }
        break;

      case "night_started":
        dispatch({ type: "NIGHT_STARTED", content: event.content });
        if (event.content) {
          ctx.onCharacterResponseRef.current?.(event.content, "Narrator");
        }
        break;

      case "night_results":
        dispatch({
          type: "NIGHT_RESULTS",
          narration: event.content || event.narration,
          eliminatedIds: event.eliminated_ids,
        });
        if (event.content || event.narration) {
          ctx.onCharacterResponseRef.current?.(
            event.content || event.narration || "", "Narrator",
          );
        }
        break;

      case "night_kill_reveal":
        if (event.character_id) {
          dispatch({
            type: "NIGHT_KILL_REVEAL",
            character: {
              id: event.character_id,
              name: event.character_name || "",
              hidden_role: event.hidden_role || "",
              faction: event.faction || "",
              win_condition: event.win_condition || "",
              hidden_knowledge: event.hidden_knowledge || [],
              behavioral_rules: event.behavioral_rules || [],
              persona: event.persona || "",
              speaking_style: "",
              avatar_seed: event.avatar_seed || "",
              public_role: event.public_role || "",
              voice_id: "",
              is_eliminated: true,
            },
          });
        }
        break;

      case "voting_started":
        dispatch({ type: "VOTING_STARTED" });
        break;

      case "vote":
        if (event.voter_name && event.target_name) {
          dispatch({
            type: "VOTE_RECEIVED",
            voterName: event.voter_name,
            targetName: event.target_name,
          });
        }
        break;

      case "tally":
        dispatch({
          type: "TALLY_RECEIVED",
          tally: event.tally || {},
          isTie: event.is_tie || false,
        });
        break;

      case "elimination":
        dispatch({
          type: "ELIMINATION",
          characterId: event.character_id,
          characterName: event.character_name,
          hiddenRole: event.hidden_role,
          faction: event.faction,
          narration: event.narration,
        });
        // Fetch full character reveal data
        if (event.character_id && event.character_id !== "player") {
          const sid = ctx.sessionRef.current?.session_id;
          if (sid) {
            api.getCharacterReveal(sid, event.character_id)
              .then((revealData) => {
                const char = ctx.sessionRef.current?.characters.find(
                  (c) => c.id === event.character_id,
                );
                dispatch({
                  type: "SET_REVEALED_CHARACTER",
                  character: {
                    ...(char as any),
                    ...revealData,
                    is_eliminated: true,
                  },
                });
              })
              .catch(() => {
                dispatch({
                  type: "SET_REVEALED_CHARACTER",
                  character: {
                    id: event.character_id!,
                    name: event.character_name || "",
                    hidden_role: event.hidden_role || "",
                    faction: event.faction || "",
                    win_condition: "",
                    hidden_knowledge: [],
                    behavioral_rules: [],
                    persona: "",
                    speaking_style: "",
                    avatar_seed: "",
                    public_role: "",
                    voice_id: "",
                    is_eliminated: true,
                  },
                });
              });
          }
        }
        break;

      case "ai_thinking":
        if (event.character_id && event.character_name && event.thinking_content) {
          dispatch({
            type: "AI_THOUGHT",
            characterId: event.character_id,
            characterName: event.character_name,
            content: event.thinking_content,
          });
        }
        break;

      case "last_words":
        if (event.content) {
          dispatch({
            type: "LAST_WORDS",
            characterId: event.character_id,
            characterName: event.character_name,
            content: event.content,
          });
        }
        break;

      case "night_action_prompt":
        if (event.action_type && event.eligible_targets) {
          dispatch({
            type: "NIGHT_ACTION_PROMPT",
            actionType: event.action_type,
            targets: event.eligible_targets,
            allies: event.allies,
          });
        }
        break;

      case "player_eliminated":
        dispatch({
          type: "PLAYER_ELIMINATED",
          hiddenRole: event.hidden_role,
          faction: event.faction,
          eliminatedBy: event.eliminated_by,
          allCharacters: event.all_characters,
          narration: event.narration,
        });
        break;

      case "investigation_result":
        if (event.investigation_result) {
          dispatch({
            type: "INVESTIGATION_RESULT",
            result: event.investigation_result,
          });
        }
        break;

      case "game_over":
        dispatch({
          type: "GAME_OVER",
          winner: event.winner || "Unknown",
          narration: event.narration,
          allCharacters: event.all_characters,
        });
        break;

      case "error":
        streamBuffer.clear();
        dispatch({ type: "SET_ERROR", error: event.error || "An error occurred" });
        break;

      case "done":
        streamBuffer.runWhenIdle(() => {
          dispatch({ type: "DONE", phase: event.phase, round: event.round, tension: event.tension });

          // Execute deferred discussion end
          if (ctx.pendingDiscussionEndRef.current) {
            ctx.pendingDiscussionEndRef.current = false;
            dispatch({
              type: "DISCUSSION_ENDING",
              content: "The council has heard enough. The vote will now begin.",
            });
          }
        });
        break;
    }
  };
}
