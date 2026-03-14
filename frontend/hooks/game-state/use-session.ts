/**
 * Session creation, recovery, and join hooks.
 */

import { useCallback, useEffect, useRef, type Dispatch } from "react";
import * as api from "@/lib/api";
import type { GameAction, GameReducerState, GameChatMessage, GameSession } from "./types";

const STORAGE_KEY = "council_session_id";

export function useSessionRecovery(
  state: GameReducerState,
  dispatch: Dispatch<GameAction>,
) {
  const hasAttemptedRecovery = useRef(false);

  // Session recovery from localStorage
  useEffect(() => {
    if (hasAttemptedRecovery.current) return;
    hasAttemptedRecovery.current = true;

    const savedId = localStorage.getItem(STORAGE_KEY);
    if (!savedId || state.session) return;

    dispatch({ type: "SET_RECOVERING", value: true });
    (async () => {
      try {
        const data = await api.getGameState(savedId, true);
        const session: GameSession = {
          session_id: data.session_id,
          world_title: data.world_title,
          world_setting: data.world_setting,
          characters: data.characters,
          phase: data.phase,
        };

        const messages: GameChatMessage[] = (data.messages || []).map((m: any) => {
          if (m.speaker_id === "player") {
            return { role: "user" as const, content: m.content };
          }
          if (m.speaker_id === "narrator" || m.speaker_id === "") {
            return { role: "narrator" as const, content: m.content };
          }
          return {
            role: "character" as const,
            characterId: m.speaker_id,
            characterName: m.speaker_name,
            content: m.content,
          };
        });

        dispatch({
          type: "SESSION_RECOVERED",
          session,
          phase: data.phase,
          round: data.round || 1,
          messages,
          voteResults: data.vote_results?.length
            ? data.vote_results[data.vote_results.length - 1]
            : undefined,
          playerRole: data.player_role,
          nightActionPrompt: data.night_action_prompt
            ? { actionType: data.night_action_prompt.action_type, targets: data.night_action_prompt.eligible_targets }
            : undefined,
          winner: data.winner,
        });
      } catch {
        localStorage.removeItem(STORAGE_KEY);
        dispatch({ type: "SET_RECOVERING", value: false });
      }
    })();
  }, []);

  // Join game via URL parameter ?session=xxx
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const joinSessionId = params.get("session");
    if (!joinSessionId || state.session) return;

    dispatch({ type: "SET_RECOVERING", value: true });
    (async () => {
      try {
        await api.joinGame(joinSessionId);
        localStorage.setItem(STORAGE_KEY, joinSessionId);
        const data = await api.getGameState(joinSessionId, true);
        const session: GameSession = {
          session_id: data.session_id,
          world_title: data.world_title,
          world_setting: data.world_setting,
          characters: data.characters,
          phase: data.phase,
        };
        dispatch({
          type: "JOIN_SUCCESS",
          session,
          phase: data.phase,
          round: data.round || 1,
          playerRole: data.player_role,
        });
        window.history.replaceState({}, "", window.location.pathname);
        dispatch({ type: "SET_ERROR", error: "Joined game successfully!" });
        setTimeout(() => dispatch({ type: "SET_ERROR", error: null }), 3000);
      } catch {
        dispatch({ type: "SET_ERROR", error: "Failed to join game session" });
        dispatch({ type: "SET_RECOVERING", value: false });
      }
    })();
  }, []);
}

export function useSessionActions(
  stateRef: { current: GameReducerState },
  dispatch: Dispatch<GameAction>,
  handleStreamEvent: (event: any) => void,
  streamRef: { current: AbortController | null },
  clearBuffers: () => void,
) {
  const HOWTOPLAY_STORAGE_KEY = "council_howtoplay_seen";

  // After session is created, immediately fetch player role so lobby shows identity
  const fetchPlayerRole = useCallback(async (sessionId: string) => {
    try {
      const role = await api.getPlayerRole(sessionId);
      dispatch({ type: "SET_PLAYER_ROLE", role });
    } catch {
      // Player role may not be assigned yet — that's fine
    }
  }, [dispatch]);

  const uploadDocument = useCallback(async (file: File, language?: string) => {
    dispatch({ type: "SET_PHASE", phase: "parsing" });
    dispatch({ type: "SET_PARSE_PROGRESS", text: "Analyzing document..." });
    dispatch({ type: "SET_ERROR", error: null });
    try {
      const sess = await api.createGameFromDocument(file, language);
      dispatch({ type: "SESSION_CREATED", session: sess });
      localStorage.setItem(STORAGE_KEY, sess.session_id);
      fetchPlayerRole(sess.session_id);
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Upload failed" });
      dispatch({ type: "SET_PHASE", phase: "upload" });
    }
  }, [dispatch, fetchPlayerRole]);

  const uploadText = useCallback(async (text: string, language?: string) => {
    dispatch({ type: "SET_PHASE", phase: "parsing" });
    dispatch({ type: "SET_PARSE_PROGRESS", text: "Generating characters..." });
    dispatch({ type: "SET_ERROR", error: null });
    try {
      const sess = await api.createGameFromText(text, language);
      dispatch({ type: "SESSION_CREATED", session: sess });
      localStorage.setItem(STORAGE_KEY, sess.session_id);
      fetchPlayerRole(sess.session_id);
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Creation failed" });
      dispatch({ type: "SET_PHASE", phase: "upload" });
    }
  }, [dispatch, fetchPlayerRole]);

  const loadScenario = useCallback(async (id: string) => {
    dispatch({ type: "SET_PHASE", phase: "parsing" });
    dispatch({ type: "SET_PARSE_PROGRESS", text: "Loading scenario..." });
    dispatch({ type: "SET_ERROR", error: null });
    try {
      const sess = await api.loadScenario(id);
      dispatch({ type: "SESSION_CREATED", session: sess });
      localStorage.setItem(STORAGE_KEY, sess.session_id);
      fetchPlayerRole(sess.session_id);
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : "Failed to load scenario" });
      dispatch({ type: "SET_PHASE", phase: "upload" });
    }
  }, [dispatch, fetchPlayerRole]);

  const startGame = useCallback(async () => {
    const session = stateRef.current.session;
    if (!session) return;
    dispatch({ type: "START_GAME_BEGIN" });

    const stages = [
      { pct: 15, text: "Assigning roles..." },
      { pct: 35, text: "Building world state..." },
      { pct: 55, text: "Awakening characters..." },
      { pct: 75, text: "Setting the scene..." },
      { pct: 90, text: "Almost ready..." },
    ];
    let stageIdx = 0;
    const progressTimer = setInterval(() => {
      if (stageIdx < stages.length) {
        dispatch({ type: "START_GAME_PROGRESS", progress: stages[stageIdx].pct, text: stages[stageIdx].text });
        stageIdx++;
      }
    }, 600);

    try {
      const result = await api.startGame(session.session_id);
      clearInterval(progressTimer);
      dispatch({ type: "START_GAME_PROGRESS", progress: 100, text: "The council awaits..." });

      try {
        const role = await api.getPlayerRole(session.session_id);
        dispatch({ type: "SET_PLAYER_ROLE", role });
      } catch {
        // Player role is optional
      }

      await new Promise((r) => setTimeout(r, 400));
      dispatch({ type: "START_GAME_COMPLETE", round: result.round || 1, narration: result.narration || null });
    } catch (err) {
      clearInterval(progressTimer);
      dispatch({ type: "START_GAME_FAILED", error: err instanceof Error ? err.message : "Failed to start game" });
    }
  }, [dispatch, stateRef]);

  const showHowToPlay = useCallback(() => {
    if (!stateRef.current.session) return;
    const seen = localStorage.getItem(HOWTOPLAY_STORAGE_KEY);
    if (seen === "true") {
      startGame();
    } else {
      dispatch({ type: "SET_PHASE", phase: "howtoplay" });
    }
  }, [dispatch, stateRef, startGame]);

  const resetGame = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.abort();
      streamRef.current = null;
    }
    clearBuffers();
    localStorage.removeItem(STORAGE_KEY);
    dispatch({ type: "GAME_RESET" });
  }, [dispatch, clearBuffers]);

  const loadScenarios = useCallback(async () => {
    try {
      const list = await api.getGameScenarios();
      dispatch({ type: "SET_SCENARIOS", scenarios: list });
    } catch {
      // scenarios are optional
    }
  }, [dispatch]);

  return {
    uploadDocument,
    uploadText,
    loadScenario,
    startGame,
    showHowToPlay,
    resetGame,
    loadScenarios,
  };
}
