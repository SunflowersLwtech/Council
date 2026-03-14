/**
 * GameStateProvider — composes reducer, sub-hooks, and context.
 * Preserves the exact same GameStateCtx interface as the original useGameState.tsx.
 */

"use client";

import {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
  useRef,
  useMemo,
  type ReactNode,
} from "react";
import { flushSync } from "react-dom";
import type {
  GamePhase,
  CharacterRevealed,
  GameSession,
  VoteResult,
  ScenarioInfo,
  PlayerRole,
  NightActionTarget,
  GameStreamEvent,
} from "@/lib/game-types";
import { usePowerSyncGameState, type PSGameCharacter } from "@/hooks/usePowerSyncGameState";

import type { GameChatMessage, AIThought, GameReducerState, NightActionState, RevealedCharacterInfo, StaggeredVote } from "./types";
import { INITIAL_STATE } from "./types";
import { gameReducer } from "./reducer";
import { StreamBuffer } from "./stream-buffer";
import { createStreamEventHandler } from "./event-handler";
import { useSessionRecovery, useSessionActions } from "./use-session";
import { useChatActions } from "./use-chat";
import { useVotingActions } from "./use-voting";
import { useNightActions } from "./use-night";
import { useAutoTriggers } from "./use-auto-triggers";

// ── Context interface (unchanged from original) ─────────────────────

interface GameStateCtx {
  phase: GamePhase;
  isRecovering: boolean;
  isStarting: boolean;
  startProgress: number;
  startStatusText: string;
  session: GameSession | null;
  chatMessages: GameChatMessage[];
  isChatStreaming: boolean;
  parseProgress: string;
  selectedVote: string | null;
  hasVoted: boolean;
  voteResults: VoteResult | null;
  revealedCharacter: CharacterRevealed | null;
  gameEnd: { winner: string } | null;
  error: string | null;
  scenarios: ScenarioInfo[];
  round: number;
  tension: number;
  chatTarget: string | null;
  introNarration: string | null;
  completeIntro: () => void;
  playerRole: PlayerRole | null;
  isGhostMode: boolean;
  nightActionRequired: { actionType: string; targets: NightActionTarget[]; allies?: Array<{ id: string; name: string; avatar_seed: string }> } | null;
  investigationResult: { name: string; faction: string } | null;
  revealedCharacters: Array<{
    id: string; name: string; hidden_role: string; faction: string;
    is_eliminated: boolean; persona: string; public_role: string; avatar_seed: string;
  }>;
  staggeredVotes: Array<{
    voterName: string; targetName: string; timestamp: number;
  }>;
  aiThoughts: AIThought[];
  uploadDocument: (file: File, language?: string) => Promise<void>;
  uploadText: (text: string, language?: string) => Promise<void>;
  loadScenario: (id: string) => Promise<void>;
  startGame: () => Promise<void>;
  showHowToPlay: () => void;
  sendMessage: (text: string, targetId?: string | null) => void;
  castVote: (charId: string) => void;
  setSelectedVote: (id: string | null) => void;
  setChatTarget: (id: string | null) => void;
  dismissReveal: () => void;
  triggerNight: () => void;
  resetGame: () => void;
  loadScenarios: () => Promise<void>;
  submitNightAction: (targetId: string) => void;
  dismissInvestigation: () => void;
  endDiscussion: () => void;
  sendNightChat: (text: string) => void;
}

const GameStateContext = createContext<GameStateCtx | null>(null);

interface GameStateProviderProps {
  children: ReactNode;
  onCharacterResponse?: (content: string, characterName: string, voiceId?: string, characterId?: string) => void;
}

export function GameStateProvider({ children, onCharacterResponse }: GameStateProviderProps) {
  const [state, dispatch] = useReducer(gameReducer, INITIAL_STATE);

  // ── Refs for stable access in callbacks ──────────────────────────
  const stateRef = useRef(state);
  stateRef.current = state;

  const streamRef = useRef<AbortController | null>(null);
  const sessionRef = useRef<GameSession | null>(state.session);
  sessionRef.current = state.session;
  const revealedCharacterRef = useRef<CharacterRevealed | null>(state.revealedCharacter);
  revealedCharacterRef.current = state.revealedCharacter;
  const deferredPhaseRef = useRef<{ phase: string; round?: number } | null>(null);
  const pendingDiscussionEndRef = useRef(false);
  const onCharacterResponseRef = useRef(onCharacterResponse);
  onCharacterResponseRef.current = onCharacterResponse;

  // ── Stream buffer ────────────────────────────────────────────────
  const streamBufferRef = useRef<StreamBuffer | null>(null);
  if (!streamBufferRef.current) {
    streamBufferRef.current = new StreamBuffer(
      // onAppend — synchronous flush for smooth rendering
      (actorKey, delta) => {
        flushSync(() => {
          dispatch({ type: "STREAM_APPEND", actorKey, delta });
        });
      },
      // onFinalize — UI state update only. TTS is triggered earlier in event-handler.ts
      (actorKey, endEvent) => {
        dispatch({
          type: "STREAM_FINALIZE",
          actorKey,
          content: endEvent.content,
          voiceId: endEvent.voice_id,
          emotion: endEvent.emotion,
        });
      },
    );
  }
  const streamBuffer = streamBufferRef.current;

  // Cleanup on unmount
  useEffect(() => {
    return () => { streamBuffer.clear(); };
  }, [streamBuffer]);

  // ── Event handler ────────────────────────────────────────────────
  const handleStreamEvent = useMemo(
    () => createStreamEventHandler({
      dispatch,
      streamBuffer,
      sessionRef,
      revealedCharacterRef,
      deferredPhaseRef,
      pendingDiscussionEndRef,
      onCharacterResponseRef,
    }),
    [streamBuffer],
  );

  // ── PowerSync integration ────────────────────────────────────────
  const ps = usePowerSyncGameState(state.psSessionId);

  // Merge PowerSync character updates (elimination status + player join detection)
  useEffect(() => {
    if (!ps.characters.length || !state.session) return;

    let hasChange = false;
    const updatedChars = state.session.characters.map((sc) => {
      const pc = ps.characters.find((p: PSGameCharacter) => p.id === sc.id);
      if (!pc) return sc;
      const newElim = !!pc.is_eliminated;
      const newIsPlayer = !!pc.is_player;
      if (newElim !== sc.is_eliminated || newIsPlayer !== (sc as any).is_player) {
        hasChange = true;
        return { ...sc, is_eliminated: newElim, is_player: newIsPlayer };
      }
      return sc;
    });

    if (hasChange) {
      dispatch({
        type: "PS_CHARACTERS_UPDATED",
        updates: updatedChars.map((c) => ({ id: c.id, is_eliminated: c.is_eliminated })),
      });
    }
  }, [ps.characters, state.session]);

  // Sync PowerSync session data (phase, round, tension, winner)
  useEffect(() => {
    if (!ps.gameSession) return;
    const psPhase = ps.gameSession.phase;
    const psRound = ps.gameSession.round;
    const psWinner = ps.gameSession.winner;

    dispatch({
      type: "PS_SESSION_UPDATED",
      winner: psWinner || undefined,
      round: psRound || undefined,
      tension: ps.gameSession.tension_level,
    });

    // If server phase advanced (e.g. friend started game), sync local phase
    if (psPhase && state.phase === "lobby" && psPhase === "discussion") {
      dispatch({ type: "SET_PHASE", phase: "discussion", round: psRound });
    }
  }, [ps.gameSession]);

  // ── Sub-hooks ────────────────────────────────────────────────────
  useSessionRecovery(state, dispatch);

  const sessionActions = useSessionActions(
    stateRef, dispatch, handleStreamEvent, streamRef,
    () => streamBuffer.clear(),
  );

  const chatActions = useChatActions(stateRef, dispatch, handleStreamEvent, streamRef);
  const votingActions = useVotingActions(stateRef, dispatch, handleStreamEvent, streamRef, pendingDiscussionEndRef);
  const nightActions = useNightActions(stateRef, dispatch, handleStreamEvent, streamRef, deferredPhaseRef);
  useAutoTriggers(stateRef, dispatch, handleStreamEvent, streamRef);

  // ── Context value ────────────────────────────────────────────────
  const contextValue: GameStateCtx = useMemo(() => ({
    // State
    phase: state.phase,
    isRecovering: state.isRecovering,
    isStarting: state.isStarting,
    startProgress: state.startProgress,
    startStatusText: state.startStatusText,
    session: state.session,
    chatMessages: state.chatMessages,
    isChatStreaming: state.isChatStreaming,
    parseProgress: state.parseProgress,
    selectedVote: state.selectedVote,
    hasVoted: state.hasVoted,
    voteResults: state.voteResults,
    revealedCharacter: state.revealedCharacter,
    gameEnd: state.gameEnd,
    error: state.error,
    scenarios: state.scenarios,
    round: state.round,
    tension: state.tension,
    chatTarget: state.chatTarget,
    introNarration: state.introNarration,
    playerRole: state.playerRole,
    isGhostMode: state.isGhostMode,
    nightActionRequired: state.nightActionRequired,
    investigationResult: state.investigationResult,
    revealedCharacters: state.revealedCharacters,
    staggeredVotes: state.staggeredVotes,
    aiThoughts: state.aiThoughts,
    // Actions
    completeIntro: nightActions.completeIntro,
    uploadDocument: sessionActions.uploadDocument,
    uploadText: sessionActions.uploadText,
    loadScenario: sessionActions.loadScenario,
    startGame: sessionActions.startGame,
    showHowToPlay: sessionActions.showHowToPlay,
    sendMessage: chatActions.sendMessage,
    castVote: votingActions.castVote,
    setSelectedVote: votingActions.setSelectedVote,
    setChatTarget: votingActions.setChatTarget,
    dismissReveal: nightActions.dismissReveal,
    triggerNight: nightActions.triggerNight,
    resetGame: sessionActions.resetGame,
    loadScenarios: sessionActions.loadScenarios,
    submitNightAction: nightActions.submitNightAction,
    dismissInvestigation: nightActions.dismissInvestigation,
    endDiscussion: votingActions.endDiscussion,
    sendNightChat: chatActions.sendNightChat,
  }), [state, sessionActions, chatActions, votingActions, nightActions]);

  return (
    <GameStateContext.Provider value={contextValue}>
      {children}
    </GameStateContext.Provider>
  );
}

export function useGameState() {
  const ctx = useContext(GameStateContext);
  if (!ctx) throw new Error("useGameState must be used within GameStateProvider");
  return ctx;
}

// Re-export types for consumers
export type { GameChatMessage, AIThought } from "./types";
