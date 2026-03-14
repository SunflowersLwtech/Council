/**
 * Night phase action hooks — submitNightAction, triggerNight, dismissInvestigation, dismissReveal.
 */

import { useCallback, type Dispatch } from "react";
import * as api from "@/lib/api";
import type { GameAction, GameReducerState, GamePhase } from "./types";

export function useNightActions(
  stateRef: { current: GameReducerState },
  dispatch: Dispatch<GameAction>,
  handleStreamEvent: (event: any) => void,
  streamRef: { current: AbortController | null },
  deferredPhaseRef: { current: { phase: string; round?: number } | null },
) {
  const submitNightAction = useCallback(
    (targetId: string) => {
      const { session, nightActionRequired, isChatStreaming } = stateRef.current;
      if (!session || !nightActionRequired || isChatStreaming) return;

      dispatch({ type: "SET_STREAMING", value: true });
      dispatch({ type: "CLEAR_NIGHT_ACTION" });

      const controller = api.streamPlayerNightAction(
        session.session_id,
        nightActionRequired.actionType,
        targetId,
        handleStreamEvent,
      );
      streamRef.current = controller;
    },
    [dispatch, stateRef, handleStreamEvent],
  );

  const triggerNight = useCallback(() => {
    const { session, isChatStreaming } = stateRef.current;
    if (!session || isChatStreaming) return;

    dispatch({ type: "SET_STREAMING", value: true });
    const controller = api.streamGameNight(
      session.session_id,
      handleStreamEvent,
    );
    streamRef.current = controller;
  }, [dispatch, stateRef, handleStreamEvent]);

  const dismissInvestigation = useCallback(() => {
    dispatch({ type: "DISMISS_INVESTIGATION" });
  }, [dispatch]);

  const dismissReveal = useCallback(() => {
    const deferred = deferredPhaseRef.current;
    deferredPhaseRef.current = null;
    dispatch({
      type: "DISMISS_REVEAL",
      deferredPhase: deferred?.phase as GamePhase | undefined,
      deferredRound: deferred?.round,
    });
  }, [dispatch, deferredPhaseRef]);

  const completeIntro = useCallback(() => {
    const narration = stateRef.current.introNarration;
    dispatch({
      type: "COMPLETE_INTRO",
      narration: narration || "The council session begins. The first debate starts now.",
    });
  }, [dispatch, stateRef]);

  return {
    submitNightAction,
    triggerNight,
    dismissInvestigation,
    dismissReveal,
    completeIntro,
  };
}
