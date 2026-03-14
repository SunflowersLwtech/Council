"use client";

import { useState } from "react";
import { Users, Play, MapPin, Link2, Check, User } from "lucide-react";
import { useGameState } from "@/hooks/useGameState";
import { useI18n } from "@/lib/i18n";
import CharacterCard from "@/components/CharacterCard";
import { usePowerSyncGameState, type PSGameCharacter } from "@/hooks/usePowerSyncGameState";

export default function GameLobby() {
  const { t } = useI18n();
  const { session, showHowToPlay, error, playerRole } = useGameState();
  const [copied, setCopied] = useState(false);

  // Watch PowerSync for live player count
  const ps = usePowerSyncGameState(session?.session_id ?? null);
  const playerCount = ps.characters.filter((c: PSGameCharacter) => c.is_player).length;

  if (!session) return null;

  return (
    <div className="flex flex-col items-center justify-center min-h-screen p-8">
      <div className="max-w-3xl w-full space-y-8">
        {/* World Title */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold welcome-gradient-text">
            {session.world_title}
          </h1>
          <p
            className="text-sm"
            style={{ color: "var(--text-muted)" }}
          >
            {t("game.lobby.title")}
          </p>
        </div>

        {/* Your Role Banner — show what character the player is */}
        {playerRole && (
          <div
            className="glass-card p-4 animate-fade-in"
            style={{
              borderColor: playerRole.allies?.length > 0 ? "rgba(239,68,68,0.3)" : "rgba(59,130,246,0.3)",
              boxShadow: `0 0 20px ${playerRole.allies?.length > 0 ? "rgba(239,68,68,0.1)" : "rgba(59,130,246,0.1)"}`,
            }}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center"
                style={{
                  backgroundColor: playerRole.allies?.length > 0 ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)",
                  color: playerRole.allies?.length > 0 ? "#ef4444" : "#3b82f6",
                }}
              >
                <User size={16} />
              </div>
              <div>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>Your Secret Identity</p>
                <p className="font-bold" style={{ color: playerRole.allies?.length > 0 ? "#ef4444" : "#3b82f6" }}>
                  {playerRole.hidden_role} — {playerRole.faction}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Setting */}
        <div className="glass-card p-6">
          <div className="flex items-center gap-2 mb-3">
            <MapPin size={14} style={{ color: "var(--accent)" }} />
            <span
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              {t("game.lobby.setting")}
            </span>
          </div>
          <p
            className="text-sm leading-relaxed"
            style={{ color: "var(--text-secondary)" }}
          >
            {session.world_setting}
          </p>
        </div>

        {/* Invite Link */}
        {session.session_id && (
          <div className="glass-card p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Link2 size={14} style={{ color: "var(--accent)" }} />
                <span
                  className="text-xs font-semibold uppercase tracking-wider"
                  style={{ color: "var(--text-muted)" }}
                >
                  Invite Players
                </span>
                {playerCount > 0 && (
                  <span
                    className="text-xs px-2 py-0.5 rounded-full"
                    style={{ backgroundColor: "rgba(34,197,94,0.15)", color: "#22c55e" }}
                  >
                    {playerCount} joined
                  </span>
                )}
              </div>
              <button
                className="demo-btn text-xs px-3 py-1.5 flex items-center gap-1.5"
                onClick={() => {
                  const url = `${window.location.origin}?session=${session.session_id}`;
                  navigator.clipboard.writeText(url).then(() => {
                    setCopied(true);
                    setTimeout(() => setCopied(false), 2000);
                  });
                }}
              >
                {copied ? <Check size={12} /> : <Link2 size={12} />}
                {copied ? "Copied!" : "Copy Invite Link"}
              </button>
            </div>
          </div>
        )}

        {/* Characters */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <Users size={14} style={{ color: "var(--accent)" }} />
            <span
              className="text-xs font-semibold uppercase tracking-wider"
              style={{ color: "var(--text-muted)" }}
            >
              {t("game.lobby.characters")} ({session.characters.length})
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {session.characters.map((char) => (
              <CharacterCard key={char.id} character={char} />
            ))}
          </div>
        </div>

        {/* Start button */}
        <div className="text-center">
          <button
            className="demo-btn text-lg px-12 py-4 flex items-center gap-3 mx-auto"
            onClick={showHowToPlay}
          >
            <Play size={20} />
            {t("game.lobby.startGame")}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div
            className="p-3 rounded-lg text-sm text-center animate-fade-in"
            style={{
              background: "rgba(239, 68, 68, 0.1)",
              color: "var(--critical)",
              border: "1px solid rgba(239, 68, 68, 0.2)",
            }}
          >
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
