"use client";

import dynamic from "next/dynamic";
import type { ReactNode } from "react";

// PowerSync uses WASM + OPFS, so it must be loaded client-side only
const PowerSyncProvider = dynamic(
  () =>
    import("@/components/providers/PowerSyncProvider").then(
      (mod) => mod.PowerSyncProvider
    ),
  { ssr: false }
);

export function ClientProviders({ children }: { children: ReactNode }) {
  return <PowerSyncProvider>{children}</PowerSyncProvider>;
}
