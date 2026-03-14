/**
 * Auto-trigger effects for night phase and open discussion.
 */

import { useEffect, useRef, type Dispatch } from "react";
import * as api from "@/lib/api";
import type { GameAction, GameReducerState } from "./types";

export function useAutoTriggers(
  stateRef: { current: GameReducerState },
  dispatch: Dispatch<GameAction>,
  handleStreamEvent: (event: any) => void,
  streamRef: { current: AbortController | null },
) {
  // Auto-trigger night phase after delay
  useEffect(() => {
    const { phase, revealedCharacter, isChatStreaming, nightActionRequired, session, gameEnd } = stateRef.current;
    if (
      phase === "night" &&
      !revealedCharacter &&
      !isChatStreaming &&
      !nightActionRequired &&
      session &&
      !gameEnd
    ) {
      const timer = setTimeout(() => {
        dispatch({ type: "SET_STREAMING", value: true });
        const controller = api.streamGameNight(
          session.session_id,
          handleStreamEvent,
        );
        streamRef.current = controller;
      }, 4500);
      return () => clearTimeout(timer);
    }
  }, [
    stateRef.current.phase,
    stateRef.current.revealedCharacter,
    stateRef.current.isChatStreaming,
    stateRef.current.nightActionRequired,
    stateRef.current.session,
    stateRef.current.gameEnd,
    handleStreamEvent,
  ]);

  // Auto-trigger structured opening discussion
  const openDiscussionTriggeredRef = useRef<number>(0);
  useEffect(() => {
    const { phase, isChatStreaming, session, gameEnd, round } = stateRef.current;
    if (
      phase === "discussion" &&
      !isChatStreaming &&
      session &&
      !gameEnd &&
      round !== openDiscussionTriggeredRef.current
    ) {
      openDiscussionTriggeredRef.current = round;
      const timer = setTimeout(() => {
        dispatch({ type: "SET_STREAMING", value: true });
        const controller = api.streamOpenDiscussion(
          session.session_id,
          handleStreamEvent,
        );
        streamRef.current = controller;
      }, 2200);
      return () => clearTimeout(timer);
    }
  }, [
    stateRef.current.phase,
    stateRef.current.isChatStreaming,
    stateRef.current.session,
    stateRef.current.gameEnd,
    stateRef.current.round,
    handleStreamEvent,
  ]);

  // Prune chat messages if they exceed 500
  useEffect(() => {
    if (stateRef.current.chatMessages.length > 500) {
      dispatch({ type: "PRUNE_MESSAGES" });
    }
  }, [stateRef.current.chatMessages.length]);
}
