/**
 * Shared types for the game state reducer system.
 */

import type {
  GamePhase,
  CharacterPublic,
  GameSession,
  VoteResult,
  CharacterRevealed,
  GameStreamEvent,
  ScenarioInfo,
  PlayerRole,
  NightActionTarget,
} from "@/lib/game-types";

// ── Re-exported domain types ────────────────────────────────────────

export interface GameChatMessage {
  role: "user" | "character" | "narrator" | "system";
  characterId?: string;
  characterName?: string;
  content: string;
  isThinking?: boolean;
  isStreaming?: boolean;
  streamActorKey?: string;
  voiceId?: string;
  isComplication?: boolean;
  emotion?: string;
  isLastWords?: boolean;
}

export interface AIThought {
  characterId: string;
  characterName: string;
  content: string;
  timestamp: number;
}

export interface NightActionState {
  actionType: string;
  targets: NightActionTarget[];
  allies?: Array<{ id: string; name: string; avatar_seed: string }>;
}

export interface RevealedCharacterInfo {
  id: string; name: string; hidden_role: string; faction: string;
  is_eliminated: boolean; persona: string; public_role: string; avatar_seed: string;
}

export interface StaggeredVote {
  voterName: string;
  targetName: string;
  timestamp: number;
}

// ── Reducer state ───────────────────────────────────────────────────

export interface GameReducerState {
  // Session & identity
  phase: GamePhase;
  session: GameSession | null;
  playerRole: PlayerRole | null;
  isGhostMode: boolean;
  revealedCharacters: RevealedCharacterInfo[];

  // Loading
  isRecovering: boolean;
  isStarting: boolean;
  startProgress: number;
  startStatusText: string;
  parseProgress: string;

  // Chat
  chatMessages: GameChatMessage[];
  isChatStreaming: boolean;
  chatTarget: string | null;

  // Voting
  selectedVote: string | null;
  hasVoted: boolean;
  voteResults: VoteResult | null;
  staggeredVotes: StaggeredVote[];

  // Phase-specific
  revealedCharacter: CharacterRevealed | null;
  gameEnd: { winner: string } | null;
  nightActionRequired: NightActionState | null;
  investigationResult: { name: string; faction: string } | null;
  introNarration: string | null;

  // Metadata
  round: number;
  tension: number;
  error: string | null;
  scenarios: ScenarioInfo[];
  aiThoughts: AIThought[];
  psSessionId: string | null;
}

export const INITIAL_STATE: GameReducerState = {
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
  scenarios: [],
  aiThoughts: [],
  psSessionId: null,
};

// ── Action types ────────────────────────────────────────────────────

export type GameAction =
  // Session lifecycle
  | { type: "SESSION_CREATED"; session: GameSession }
  | { type: "SESSION_RECOVERED"; session: GameSession; phase: GamePhase; round: number; messages?: GameChatMessage[]; voteResults?: VoteResult; playerRole?: PlayerRole; nightActionPrompt?: NightActionState; winner?: string }
  | { type: "JOIN_SUCCESS"; session: GameSession; phase: GamePhase; round: number; playerRole?: PlayerRole }
  | { type: "GAME_RESET" }
  | { type: "SET_SCENARIOS"; scenarios: ScenarioInfo[] }
  | { type: "SET_RECOVERING"; value: boolean }
  // Phase transitions
  | { type: "SET_PHASE"; phase: GamePhase; round?: number }
  | { type: "COMPLETE_INTRO"; narration: string }
  | { type: "START_GAME_BEGIN" }
  | { type: "START_GAME_PROGRESS"; progress: number; text: string }
  | { type: "START_GAME_COMPLETE"; round: number; narration: string | null }
  | { type: "START_GAME_FAILED"; error: string }
  | { type: "SET_STARTING"; value: boolean }
  // Chat
  | { type: "ADD_MESSAGE"; message: GameChatMessage }
  | { type: "ADD_THINKING"; characterId?: string; characterName?: string }
  | { type: "STREAM_START"; characterId?: string; characterName?: string; actorKey: string }
  | { type: "STREAM_APPEND"; actorKey: string; delta: string }
  | { type: "STREAM_FINALIZE"; actorKey: string; content?: string; voiceId?: string; emotion?: string }
  | { type: "SET_STREAMING"; value: boolean }
  | { type: "SET_CHAT_TARGET"; target: string | null }
  | { type: "PRUNE_MESSAGES" }
  // Voting
  | { type: "VOTING_STARTED" }
  | { type: "VOTE_RECEIVED"; voterName: string; targetName: string }
  | { type: "TALLY_RECEIVED"; tally: Record<string, number>; isTie: boolean }
  | { type: "ELIMINATION"; characterId?: string; characterName?: string; hiddenRole?: string; faction?: string; narration?: string }
  | { type: "SET_SELECTED_VOTE"; id: string | null }
  | { type: "SET_HAS_VOTED"; value: boolean }
  // Night
  | { type: "NIGHT_STARTED"; content?: string }
  | { type: "NIGHT_ACTION_PROMPT"; actionType: string; targets: NightActionTarget[]; allies?: Array<{ id: string; name: string; avatar_seed: string }> }
  | { type: "CLEAR_NIGHT_ACTION" }
  | { type: "NIGHT_ACTION"; characterName?: string }
  | { type: "NIGHT_RESULTS"; narration?: string; eliminatedIds?: string[] }
  | { type: "NIGHT_KILL_REVEAL"; character: CharacterRevealed }
  | { type: "INVESTIGATION_RESULT"; result: { name: string; faction: string } }
  | { type: "DISMISS_INVESTIGATION" }
  // Player state
  | { type: "SET_PLAYER_ROLE"; role: PlayerRole }
  | { type: "PLAYER_ELIMINATED"; hiddenRole?: string; faction?: string; eliminatedBy?: string; allCharacters?: RevealedCharacterInfo[]; narration?: string }
  | { type: "SET_REVEALED_CHARACTER"; character: CharacterRevealed | null }
  | { type: "DISMISS_REVEAL"; deferredPhase?: GamePhase; deferredRound?: number }
  // PowerSync merge
  | { type: "PS_SESSION_UPDATED"; winner?: string; round?: number; tension?: number }
  | { type: "PS_CHARACTERS_UPDATED"; updates: Array<{ id: string; is_eliminated: boolean }> }
  // Events
  | { type: "AI_THOUGHT"; characterId: string; characterName: string; content: string }
  | { type: "GAME_OVER"; winner: string; narration?: string; allCharacters?: RevealedCharacterInfo[] }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "COMPLICATION"; content: string; tension?: number }
  | { type: "DISCUSSION_WARNING"; content: string }
  | { type: "DISCUSSION_ENDING"; content: string }
  | { type: "NARRATION"; content: string; phase?: string; round?: number }
  | { type: "LAST_WORDS"; characterId?: string; characterName?: string; content: string }
  | { type: "DONE"; phase?: string; round?: number; tension?: number }
  | { type: "SET_PS_SESSION_ID"; id: string | null }
  // Parse
  | { type: "SET_PARSE_PROGRESS"; text: string }
  // Intro
  | { type: "SET_INTRO_NARRATION"; narration: string | null };

// Re-export types from game-types for convenience
export type {
  GamePhase,
  CharacterPublic,
  GameSession,
  VoteResult,
  CharacterRevealed,
  GameStreamEvent,
  ScenarioInfo,
  PlayerRole,
  NightActionTarget,
};
