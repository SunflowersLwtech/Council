/**
 * Re-export from refactored game-state module.
 * All consumers import from this file — no changes needed.
 */
export { GameStateProvider, useGameState } from "./game-state";
export type { GameChatMessage, AIThought } from "./game-state";
