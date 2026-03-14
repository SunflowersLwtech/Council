import { column, Schema, Table } from "@powersync/web";

const game_sessions = new Table({
  session_id: column.text,
  world_title: column.text,
  phase: column.text,
  round: column.integer,
  player_count: column.integer,
  winner: column.text,
  is_active: column.integer,
  tension_level: column.real,
  awaiting_player_night_action: column.integer,
  active_skills: column.text,
  created_at: column.text,
  updated_at: column.text,
});

const game_characters = new Table({
  session_id: column.text,
  name: column.text,
  public_role: column.text,
  persona: column.text,
  avatar: column.text,
  speaking_style: column.text,
  is_eliminated: column.integer,
  is_player: column.integer,
  emotional_state: column.text,
  relationships: column.text,
  faction: column.text,
  hidden_role: column.text,
  win_condition: column.text,
  hidden_knowledge: column.text,
  player_user_id: column.text,
});

const game_messages = new Table({
  session_id: column.text,
  speaker_id: column.text,
  speaker_name: column.text,
  content: column.text,
  phase: column.text,
  round: column.integer,
  message_type: column.text,
  dominant_emotion: column.text,
  created_at: column.text,
});

const game_votes = new Table({
  session_id: column.text,
  round: column.integer,
  voter_id: column.text,
  voter_name: column.text,
  target_id: column.text,
  target_name: column.text,
  created_at: column.text,
});

const game_night_actions = new Table({
  session_id: column.text,
  round: column.integer,
  character_id: column.text,
  character_name: column.text,
  action_type: column.text,
  target_id: column.text,
  result: column.text,
  created_at: column.text,
});

export const AppSchema = new Schema({
  game_sessions,
  game_characters,
  game_messages,
  game_votes,
  game_night_actions,
});

export type Database = (typeof AppSchema)["types"];
