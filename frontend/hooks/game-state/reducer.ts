/**
 * Pure reducer for COUNCIL game state.
 * All state transitions are handled here as pure functions.
 */

import type { GameReducerState, GameAction, GameChatMessage, INITIAL_STATE as _init } from "./types";
import { isValidTransition } from "@/lib/phase-machine";

export function gameReducer(state: GameReducerState, action: GameAction): GameReducerState {
  switch (action.type) {
    // ── Session lifecycle ────────────────────────────────────────────

    case "SESSION_CREATED":
      return {
        ...state,
        session: action.session,
        phase: "lobby",
        parseProgress: "",
        error: null,
        psSessionId: action.session.session_id,
      };

    case "SESSION_RECOVERED":
      return {
        ...state,
        session: action.session,
        phase: action.phase === "intro" ? "discussion" : action.phase,
        round: action.round || 1,
        chatMessages: action.messages || [],
        voteResults: action.voteResults || null,
        playerRole: action.playerRole || null,
        isGhostMode: action.playerRole?.is_eliminated || false,
        nightActionRequired: action.nightActionPrompt || null,
        gameEnd: action.winner ? { winner: action.winner } : null,
        psSessionId: action.session.session_id,
        isRecovering: false,
      };

    case "JOIN_SUCCESS":
      return {
        ...state,
        session: action.session,
        phase: action.phase === "intro" ? "discussion" : action.phase,
        round: action.round || 1,
        playerRole: action.playerRole || null,
        psSessionId: action.session.session_id,
        isRecovering: false,
      };

    case "GAME_RESET":
      return {
        phase: "upload",
        session: null,
        playerRole: null,
        isGhostMode: false,
        revealedCharacters: [],
        isRecovering: false,
        isStarting: false,
        startProgress: 0,
        startStatusText: "Preparing the council...",
        parseProgress: "",
        chatMessages: [],
        isChatStreaming: false,
        chatTarget: null,
        selectedVote: null,
        hasVoted: false,
        voteResults: null,
        staggeredVotes: [],
        revealedCharacter: null,
        gameEnd: null,
        nightActionRequired: null,
        investigationResult: null,
        introNarration: null,
        round: 1,
        tension: 0.2,
        error: null,
        scenarios: state.scenarios, // keep loaded scenarios
        aiThoughts: [],
        psSessionId: null,
      };

    case "SET_SCENARIOS":
      return { ...state, scenarios: action.scenarios };

    case "SET_RECOVERING":
      return { ...state, isRecovering: action.value };

    // ── Phase transitions ────────────────────────────────────────────

    case "SET_PHASE":
      if (process.env.NODE_ENV === "development" && !isValidTransition(state.phase, action.phase)) {
        console.warn(`[phase-machine] Invalid transition: ${state.phase} → ${action.phase}`);
      }
      return {
        ...state,
        phase: action.phase,
        ...(action.round !== undefined ? { round: action.round } : {}),
      };

    case "COMPLETE_INTRO":
      return {
        ...state,
        phase: "discussion",
        chatMessages: [{
          role: "narrator",
          content: action.narration || "The council session begins. The first debate starts now.",
        }],
        introNarration: null,
      };

    case "START_GAME_BEGIN":
      return {
        ...state,
        isStarting: true,
        startProgress: 0,
        startStatusText: "Preparing the council...",
        error: null,
      };

    case "START_GAME_PROGRESS":
      return {
        ...state,
        startProgress: action.progress,
        startStatusText: action.text,
      };

    case "START_GAME_COMPLETE":
      return {
        ...state,
        round: action.round,
        introNarration: action.narration,
        phase: "intro",
        isStarting: false,
        startProgress: 0,
      };

    case "START_GAME_FAILED":
      return {
        ...state,
        error: action.error,
        isStarting: false,
        startProgress: 0,
      };

    case "SET_STARTING":
      return { ...state, isStarting: action.value };

    // ── Chat ─────────────────────────────────────────────────────────

    case "ADD_MESSAGE":
      return { ...state, chatMessages: [...state.chatMessages, action.message] };

    case "ADD_THINKING":
      return {
        ...state,
        chatMessages: [...state.chatMessages, {
          role: "character" as const,
          characterId: action.characterId,
          characterName: action.characterName,
          content: "",
          isThinking: true,
        }],
      };

    case "STREAM_START": {
      // Replace thinking placeholder with empty streaming message
      const filtered = state.chatMessages.filter(
        (m) => !(m.isThinking && (
          (action.characterId && m.characterId === action.characterId) ||
          (!action.characterId && action.characterName && m.characterName === action.characterName)
        ))
      );
      return {
        ...state,
        chatMessages: [
          ...filtered,
          {
            role: "character" as const,
            characterId: action.characterId,
            characterName: action.characterName,
            content: "",
            isStreaming: true,
            streamActorKey: action.actorKey,
          },
        ],
      };
    }

    case "STREAM_APPEND": {
      const idx = state.chatMessages.findLastIndex(
        (m) => m.isStreaming && m.streamActorKey === action.actorKey
      );
      if (idx === -1) return state;
      const updated = [...state.chatMessages];
      updated[idx] = {
        ...updated[idx],
        content: updated[idx].content + action.delta,
      };
      return { ...state, chatMessages: updated };
    }

    case "STREAM_FINALIZE": {
      const idx = state.chatMessages.findLastIndex(
        (m) => m.isStreaming && m.streamActorKey === action.actorKey
      );
      if (idx === -1) {
        if (!action.content) return state;
        return {
          ...state,
          chatMessages: [...state.chatMessages, {
            role: "character" as const,
            content: action.content,
            voiceId: action.voiceId,
            emotion: action.emotion,
          }],
        };
      }
      const updated = [...state.chatMessages];
      updated[idx] = {
        ...updated[idx],
        content: action.content || updated[idx].content,
        isStreaming: false,
        voiceId: action.voiceId,
        emotion: action.emotion,
        streamActorKey: undefined,
      };
      return { ...state, chatMessages: updated };
    }

    case "SET_STREAMING":
      return { ...state, isChatStreaming: action.value };

    case "SET_CHAT_TARGET":
      return { ...state, chatTarget: action.target };

    case "PRUNE_MESSAGES":
      return state.chatMessages.length > 500
        ? { ...state, chatMessages: state.chatMessages.slice(-400) }
        : state;

    // ── Voting ───────────────────────────────────────────────────────

    case "VOTING_STARTED":
      return {
        ...state,
        phase: "voting",
        hasVoted: false,
        voteResults: null,
        selectedVote: null,
        staggeredVotes: [],
        chatMessages: [...state.chatMessages, {
          role: "system" as const,
          content: "Time to vote. Select the council member you believe is a traitor.",
        }],
      };

    case "VOTE_RECEIVED":
      return {
        ...state,
        staggeredVotes: [...state.staggeredVotes, {
          voterName: action.voterName,
          targetName: action.targetName,
          timestamp: Date.now(),
        }],
      };

    case "TALLY_RECEIVED":
      return {
        ...state,
        voteResults: {
          votes: state.voteResults?.votes || [],
          tally: action.tally,
          eliminated_id: state.voteResults?.eliminated_id || null,
          eliminated_name: state.voteResults?.eliminated_name || null,
          is_tie: action.isTie,
        },
      };

    case "ELIMINATION": {
      let newSession = state.session;
      if (state.session && action.characterId) {
        newSession = {
          ...state.session,
          characters: state.session.characters.map((c) =>
            c.id === action.characterId ? { ...c, is_eliminated: true } : c
          ),
        };
      }
      return {
        ...state,
        session: newSession,
        phase: "reveal",
        voteResults: state.voteResults ? {
          ...state.voteResults,
          eliminated_id: action.characterId || null,
          eliminated_name: action.characterName || null,
        } : state.voteResults,
        chatMessages: [...state.chatMessages, {
          role: "narrator" as const,
          content: action.narration || `${action.characterName} has been eliminated. They were a ${action.hiddenRole} of the ${action.faction}.`,
        }],
      };
    }

    case "SET_SELECTED_VOTE":
      return { ...state, selectedVote: action.id };

    case "SET_HAS_VOTED":
      return { ...state, hasVoted: action.value };

    // ── Night ────────────────────────────────────────────────────────

    case "NIGHT_STARTED":
      return {
        ...state,
        phase: "night",
        chatMessages: [...state.chatMessages,
          { role: "narrator" as const, content: action.content || "Night falls... The hidden forces move in darkness." },
          { role: "system" as const, content: "Night falls. You have no night action \u2014 wait for dawn." },
        ],
      };

    case "NIGHT_ACTION_PROMPT": {
      const allyNames = action.allies?.map(a => a.name).join(", ");
      const allyMsg = allyNames ? ` Your allies: ${allyNames}.` : "";
      return {
        ...state,
        nightActionRequired: {
          actionType: action.actionType,
          targets: action.targets,
          allies: action.allies,
        },
        chatMessages: [...state.chatMessages, {
          role: "system" as const,
          content: `Night falls. You may perform your action: ${action.actionType}. Select your target below.${allyMsg}`,
        }],
      };
    }

    case "CLEAR_NIGHT_ACTION":
      return { ...state, nightActionRequired: null };

    case "NIGHT_ACTION":
      return {
        ...state,
        chatMessages: [...state.chatMessages, {
          role: "system" as const,
          content: `${action.characterName || "Someone"} performs a mysterious action...`,
        }],
      };

    case "NIGHT_RESULTS": {
      let newSession = state.session;
      const ids = action.eliminatedIds || [];
      if (ids.length > 0 && state.session) {
        const eliminatedSet = new Set(ids);
        newSession = {
          ...state.session,
          characters: state.session.characters.map((c) =>
            eliminatedSet.has(c.id) ? { ...c, is_eliminated: true } : c
          ),
        };
      }
      return {
        ...state,
        session: newSession,
        chatMessages: [...state.chatMessages, {
          role: "narrator" as const,
          content: action.narration || "Dawn breaks... The results of the night are revealed.",
        }],
      };
    }

    case "NIGHT_KILL_REVEAL":
      return { ...state, revealedCharacter: action.character };

    case "INVESTIGATION_RESULT":
      return { ...state, investigationResult: action.result };

    case "DISMISS_INVESTIGATION":
      return { ...state, investigationResult: null };

    // ── Player state ─────────────────────────────────────────────────

    case "SET_PLAYER_ROLE":
      return { ...state, playerRole: action.role };

    case "PLAYER_ELIMINATED":
      return {
        ...state,
        isGhostMode: true,
        revealedCharacters: action.allCharacters || state.revealedCharacters,
        playerRole: state.playerRole
          ? { ...state.playerRole, is_eliminated: true, eliminated_by: action.eliminatedBy || "" }
          : state.playerRole,
        chatMessages: [...state.chatMessages, {
          role: "narrator" as const,
          content: action.narration || `You have been eliminated. You were a ${action.hiddenRole} of the ${action.faction}. Entering ghost mode...`,
        }],
      };

    case "SET_REVEALED_CHARACTER":
      return { ...state, revealedCharacter: action.character };

    case "DISMISS_REVEAL":
      return {
        ...state,
        revealedCharacter: null,
        ...(action.deferredPhase ? { phase: action.deferredPhase } : {}),
        ...(action.deferredRound !== undefined ? { round: action.deferredRound } : {}),
      };

    // ── PowerSync merge ──────────────────────────────────────────────

    case "PS_SESSION_UPDATED":
      return {
        ...state,
        ...(action.winner && !state.gameEnd ? { gameEnd: { winner: action.winner } } : {}),
        ...(action.round !== undefined && action.round !== state.round ? { round: action.round } : {}),
        ...(action.tension !== undefined && action.tension !== state.tension ? { tension: action.tension } : {}),
      };

    case "PS_CHARACTERS_UPDATED": {
      if (!state.session) return state;
      const updateMap = new Map(action.updates.map(u => [u.id, u.is_eliminated]));
      const hasChange = state.session.characters.some(c => {
        const updated = updateMap.get(c.id);
        return updated !== undefined && updated !== c.is_eliminated;
      });
      if (!hasChange) return state;
      return {
        ...state,
        session: {
          ...state.session,
          characters: state.session.characters.map(c => {
            const updated = updateMap.get(c.id);
            return updated !== undefined && updated !== c.is_eliminated
              ? { ...c, is_eliminated: updated }
              : c;
          }),
        },
      };
    }

    // ── Events ───────────────────────────────────────────────────────

    case "AI_THOUGHT":
      return {
        ...state,
        aiThoughts: [...state.aiThoughts, {
          characterId: action.characterId,
          characterName: action.characterName,
          content: action.content,
          timestamp: Date.now(),
        }],
      };

    case "GAME_OVER":
      return {
        ...state,
        gameEnd: { winner: action.winner },
        phase: "ended",
        revealedCharacters: action.allCharacters || state.revealedCharacters,
        chatMessages: [...state.chatMessages, {
          role: "narrator" as const,
          content: action.narration || `Game over! ${action.winner} wins!`,
        }],
      };

    case "SET_ERROR":
      return {
        ...state,
        error: action.error,
        ...(action.error ? { isChatStreaming: false } : {}),
      };

    case "COMPLICATION":
      return {
        ...state,
        chatMessages: [...state.chatMessages, {
          role: "narrator" as const,
          content: action.content || "Something unexpected happens...",
          isComplication: true,
        }],
        ...(action.tension !== undefined ? { tension: action.tension } : {}),
      };

    case "DISCUSSION_WARNING":
      return {
        ...state,
        chatMessages: [...state.chatMessages, {
          role: "system" as const,
          content: action.content,
        }],
      };

    case "DISCUSSION_ENDING":
      return {
        ...state,
        phase: "voting",
        hasVoted: false,
        voteResults: null,
        selectedVote: null,
        staggeredVotes: [],
        chatMessages: [...state.chatMessages, {
          role: "system" as const,
          content: action.content,
        }],
      };

    case "NARRATION": {
      const msgs: GameChatMessage[] = [...state.chatMessages, {
        role: "narrator" as const,
        content: action.content,
      }];
      let s: GameReducerState = { ...state, chatMessages: msgs };
      if (action.phase) {
        s.phase = action.phase as GameReducerState["phase"];
        if (action.round) s.round = action.round;
        if (action.phase === "voting") {
          s = {
            ...s,
            hasVoted: false,
            voteResults: null,
            selectedVote: null,
            staggeredVotes: [],
            chatMessages: [...msgs, {
              role: "system" as const,
              content: "Time to vote. Select the council member you believe is a traitor.",
            }],
          };
        }
        if (action.phase === "discussion" && action.round && action.round > 1) {
          s.chatMessages = [...s.chatMessages, {
            role: "system" as const,
            content: "A new day dawns. The council is back in session \u2014 discuss what happened and plan your next move.",
          }];
        }
      }
      return s;
    }

    case "LAST_WORDS":
      return {
        ...state,
        chatMessages: [...state.chatMessages, {
          role: "character" as const,
          characterId: action.characterId,
          characterName: action.characterName,
          content: action.content,
          isLastWords: true,
        }],
      };

    case "DONE":
      return {
        ...state,
        isChatStreaming: false,
        ...(action.phase ? { phase: action.phase as GameReducerState["phase"] } : {}),
        ...(action.round !== undefined ? { round: action.round } : {}),
        ...(action.tension !== undefined ? { tension: action.tension } : {}),
      };

    case "SET_PS_SESSION_ID":
      return { ...state, psSessionId: action.id };

    case "SET_PARSE_PROGRESS":
      return { ...state, parseProgress: action.text };

    case "SET_INTRO_NARRATION":
      return { ...state, introNarration: action.narration };

    default:
      return state;
  }
}
