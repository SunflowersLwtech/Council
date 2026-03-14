/**
 * Chat action hooks — sendMessage and sendNightChat.
 */

import { useCallback, type Dispatch } from "react";
import * as api from "@/lib/api";
import type { GameAction, GameReducerState } from "./types";

export function useChatActions(
  stateRef: { current: GameReducerState },
  dispatch: Dispatch<GameAction>,
  handleStreamEvent: (event: any) => void,
  streamRef: { current: AbortController | null },
) {
  const sendMessage = useCallback(
    (text: string, targetId?: string | null) => {
      const { session, isChatStreaming, isGhostMode, chatTarget } = stateRef.current;
      if (!session || isChatStreaming || isGhostMode) return;

      const target = targetId ?? chatTarget;
      const targetChar = target
        ? session.characters.find((c) => c.id === target)
        : null;

      dispatch({
        type: "ADD_MESSAGE",
        message: {
          role: "user",
          content: targetChar ? `@${targetChar.name} ${text}` : text,
        },
      });
      dispatch({ type: "SET_STREAMING", value: true });
      dispatch({ type: "SET_CHAT_TARGET", target: null });

      const controller = api.streamGameChat(
        session.session_id,
        text,
        target ?? null,
        handleStreamEvent,
      );
      streamRef.current = controller;
    },
    [dispatch, stateRef, handleStreamEvent],
  );

  const sendNightChat = useCallback(
    (text: string) => {
      const { session, isChatStreaming } = stateRef.current;
      if (!session || isChatStreaming) return;

      dispatch({
        type: "ADD_MESSAGE",
        message: { role: "user", content: text },
      });
      dispatch({ type: "SET_STREAMING", value: true });

      const controller = api.streamNightChat(
        session.session_id,
        text,
        handleStreamEvent,
      );
      streamRef.current = controller;
    },
    [dispatch, stateRef, handleStreamEvent],
  );

  return { sendMessage, sendNightChat };
}
