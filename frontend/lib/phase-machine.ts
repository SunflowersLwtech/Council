/**
 * Unified game phase state machine — shared definition for client-side validation.
 *
 * Server phases mirror backend/game/state.py TRANSITIONS.
 * Client phases extend with upload/parsing/howtoplay/intro client-only stages.
 */

export type ServerPhase = "lobby" | "discussion" | "voting" | "reveal" | "night" | "ended";
export type ClientPhase = "upload" | "parsing" | "howtoplay" | "intro";
export type GamePhase = ServerPhase | ClientPhase;

// Mirror of backend/game/state.py TRANSITIONS
const SERVER_TRANSITIONS: Record<ServerPhase, ServerPhase[]> = {
  lobby: ["discussion"],
  discussion: ["voting"],
  voting: ["reveal"],
  reveal: ["night", "ended"],
  night: ["discussion"],
  ended: [],
};

// Full client transitions (includes client-only phases)
const CLIENT_TRANSITIONS: Record<GamePhase, GamePhase[]> = {
  upload: ["parsing"],
  parsing: ["lobby", "upload"],
  lobby: ["howtoplay", "discussion"],
  howtoplay: ["intro", "discussion"],
  intro: ["discussion"],
  discussion: ["voting"],
  voting: ["reveal"],
  reveal: ["night", "ended"],
  night: ["discussion"],
  ended: ["upload"],
};

/**
 * Check if a phase transition is valid according to the client state machine.
 * Used for development-time warnings — server remains authoritative.
 */
export function isValidTransition(from: GamePhase, to: GamePhase): boolean {
  const allowed = CLIENT_TRANSITIONS[from];
  return allowed ? allowed.includes(to) : false;
}

/** Type guard for server-side phases. */
export function isServerPhase(phase: GamePhase): phase is ServerPhase {
  return phase in SERVER_TRANSITIONS;
}

/** Type guard for client-only phases. */
export function isClientPhase(phase: GamePhase): phase is ClientPhase {
  return !isServerPhase(phase);
}
