"use client";

import { useQuery, usePowerSync } from "@powersync/react";

export interface PSGameSession {
  id: string;
  session_id: string;
  world_title: string;
  phase: string;
  round: number;
  player_count: number;
  winner: string | null;
  is_active: number;
  tension_level: number;
  awaiting_player_night_action: number;
  active_skills: string | null;
  created_at: string;
  updated_at: string;
}

export interface PSGameCharacter {
  id: string;
  session_id: string;
  name: string;
  public_role: string;
  persona: string;
  avatar: string;
  speaking_style: string;
  is_eliminated: number;
  is_player: number;
  emotional_state: string | null;
  relationships: string | null;
  faction: string | null;
  hidden_role: string | null;
  win_condition: string | null;
  hidden_knowledge: string | null;
  player_user_id: string | null;
}

export interface PSGameMessage {
  id: string;
  session_id: string;
  speaker_id: string;
  speaker_name: string;
  content: string;
  phase: string;
  round: number;
  message_type: string;
  dominant_emotion: string | null;
  created_at: string;
}

export interface PSGameVote {
  id: string;
  session_id: string;
  round: number;
  voter_id: string;
  voter_name: string;
  target_id: string;
  target_name: string;
  created_at: string;
}

export interface PSNightAction {
  id: string;
  session_id: string;
  round: number;
  character_id: string;
  character_name: string;
  action_type: string;
  target_id: string;
  result: string | null;
  created_at: string;
}

const DEFAULT_STATUS = {
  connected: false,
  lastSyncedAt: null as Date | null,
  hasSynced: false,
};

export function usePowerSyncGameState(sessionId: string | null) {
  // Safely check sync status — may be null before PowerSync context is available
  let syncStatus = DEFAULT_STATUS;
  try {
    const db = usePowerSync();
    if (db) {
      syncStatus = {
        connected: db.connected,
        lastSyncedAt: null,
        hasSynced: db.connected,
      };
    }
  } catch {
    // PowerSync context not available yet — use defaults
  }

  // Query game session
  const { data: sessions } = useQuery<PSGameSession>(
    sessionId
      ? "SELECT * FROM game_sessions WHERE session_id = ? LIMIT 1"
      : "SELECT * FROM game_sessions WHERE 1=0",
    sessionId ? [sessionId] : []
  );

  // Query characters
  const { data: characters } = useQuery<PSGameCharacter>(
    sessionId
      ? "SELECT * FROM game_characters WHERE session_id = ? ORDER BY name"
      : "SELECT * FROM game_characters WHERE 1=0",
    sessionId ? [sessionId] : []
  );

  // Query messages (last 200 to keep performant)
  const { data: messages } = useQuery<PSGameMessage>(
    sessionId
      ? "SELECT * FROM game_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT 200"
      : "SELECT * FROM game_messages WHERE 1=0",
    sessionId ? [sessionId] : []
  );

  // Query votes for current round
  const currentRound = sessions?.[0]?.round ?? 1;
  const { data: votes } = useQuery<PSGameVote>(
    sessionId
      ? "SELECT * FROM game_votes WHERE session_id = ? AND round = ? ORDER BY created_at ASC"
      : "SELECT * FROM game_votes WHERE 1=0",
    sessionId ? [sessionId, currentRound] : []
  );

  // Query night actions for current round
  const { data: nightActions } = useQuery<PSNightAction>(
    sessionId
      ? "SELECT * FROM game_night_actions WHERE session_id = ? AND round = ? ORDER BY created_at ASC"
      : "SELECT * FROM game_night_actions WHERE 1=0",
    sessionId ? [sessionId, currentRound] : []
  );

  const gameSession = sessions?.[0] ?? null;

  return {
    // Sync status
    connected: syncStatus.connected,
    lastSyncedAt: syncStatus.lastSyncedAt,
    hasSynced: syncStatus.hasSynced,

    // Data
    gameSession,
    characters: characters ?? [],
    messages: messages ?? [],
    votes: votes ?? [],
    nightActions: nightActions ?? [],
  };
}
