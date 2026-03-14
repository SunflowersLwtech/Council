/**
 * Voting action hooks — castVote, endDiscussion, setSelectedVote.
 */

import { useCallback, type Dispatch } from "react";
import * as api from "@/lib/api";
import type { GameAction, GameReducerState } from "./types";

export function useVotingActions(
  stateRef: { current: GameReducerState },
  dispatch: Dispatch<GameAction>,
  handleStreamEvent: (event: any) => void,
  streamRef: { current: AbortController | null },
  pendingDiscussionEndRef: { current: boolean },
) {
  const castVote = useCallback(
    (charId: string) => {
      const { session, hasVoted, isGhostMode } = stateRef.current;
      if (!session || hasVoted || isGhostMode) return;

      dispatch({ type: "SET_HAS_VOTED", value: true });
      dispatch({ type: "SET_STREAMING", value: true });

      const controller = api.streamGameVote(
        session.session_id,
        charId,
        handleStreamEvent,
      );
      streamRef.current = controller;
    },
    [dispatch, stateRef, handleStreamEvent],
  );

  const setSelectedVote = useCallback(
    (id: string | null) => {
      dispatch({ type: "SET_SELECTED_VOTE", id });
    },
    [dispatch],
  );

  const setChatTarget = useCallback(
    (id: string | null) => {
      dispatch({ type: "SET_CHAT_TARGET", target: id });
    },
    [dispatch],
  );

  const endDiscussion = useCallback(() => {
    const { phase, isChatStreaming } = stateRef.current;
    if (phase !== "discussion") return;
    if (isChatStreaming) {
      pendingDiscussionEndRef.current = true;
      return;
    }
    dispatch({
      type: "DISCUSSION_ENDING",
      content: "The council has heard enough. The vote will now begin.",
    });
  }, [dispatch, stateRef, pendingDiscussionEndRef]);

  return { castVote, setSelectedVote, setChatTarget, endDiscussion };
}
