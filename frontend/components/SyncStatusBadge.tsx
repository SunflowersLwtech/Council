"use client";

import { usePowerSync } from "@powersync/react";

/**
 * Displays PowerSync connection status as a small badge.
 * Shows Synced (green), Offline (yellow), or Syncing (animated).
 */
export default function SyncStatusBadge() {
  const powerSync = usePowerSync();
  const connected = powerSync.connected;
  // currentStatus is a PowerSyncConnectionStatus enum or similar
  const connecting = !connected && powerSync.currentStatus?.dataFlowStatus?.downloading;

  let label: string;
  let dotColor: string;
  let animate = false;

  if (connected) {
    label = "Synced";
    dotColor = "#22c55e"; // green-500
  } else if (connecting) {
    label = "Syncing...";
    dotColor = "#f59e0b"; // amber-500
    animate = true;
  } else {
    label = "Offline";
    dotColor = "#f59e0b"; // amber-500
  }

  return (
    <div
      className="sync-status-badge"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        padding: "3px 8px",
        borderRadius: "12px",
        backgroundColor: "rgba(255,255,255,0.06)",
        fontSize: "11px",
        color: "var(--text-dim, #a0a0a0)",
        userSelect: "none",
      }}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          backgroundColor: dotColor,
          display: "inline-block",
          ...(animate ? { animation: "pulse 1.5s ease-in-out infinite" } : {}),
        }}
      />
      {label}
    </div>
  );
}
