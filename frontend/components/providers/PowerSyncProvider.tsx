"use client";

import { useEffect, useState, type ReactNode } from "react";
import { PowerSyncContext } from "@powersync/react";
import {
  PowerSyncDatabase,
  WASQLiteOpenFactory,
  WASQLiteVFS,
} from "@powersync/web";
import { AppSchema } from "@/lib/powersync";
import { SupabaseConnector } from "@/lib/powersync-connector";
import { supabase } from "@/lib/supabase";

let _db: PowerSyncDatabase | null = null;

function getDB(): PowerSyncDatabase {
  if (!_db) {
    _db = new PowerSyncDatabase({
      schema: AppSchema,
      database: new WASQLiteOpenFactory({
        dbFilename: "council.db",
        vfs: WASQLiteVFS.OPFSCoopSyncVFS,
        flags: {
          enableMultiTabs: typeof SharedWorker !== "undefined",
        },
      }),
    });
  }
  return _db;
}

export function PowerSyncProvider({ children }: { children: ReactNode }) {
  const [db, setDb] = useState<PowerSyncDatabase | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function init() {
      const database = getDB();
      const connector = new SupabaseConnector();

      // Wait for a valid Supabase session before connecting
      const {
        data: { session },
      } = await supabase.auth.getSession();

      if (session && !cancelled) {
        try {
          await database.connect(connector);
        } catch (err) {
          console.warn("[PowerSync] connect error (non-fatal):", err);
        }
      }

      if (!cancelled) {
        setDb(database);
      }

      // Re-connect when auth state changes (login / token refresh)
      const {
        data: { subscription },
      } = supabase.auth.onAuthStateChange(async (event) => {
        if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED") {
          try {
            await database.connect(new SupabaseConnector());
          } catch (err) {
            console.warn("[PowerSync] reconnect error:", err);
          }
        }
        if (event === "SIGNED_OUT") {
          try {
            await database.disconnect();
          } catch {
            // ignore
          }
        }
      });

      return () => {
        subscription.unsubscribe();
      };
    }

    const cleanupPromise = init();

    return () => {
      cancelled = true;
      cleanupPromise.then((unsub) => unsub?.());
    };
  }, []);

  // Always render children. PowerSync hooks handle null db gracefully.
  // When db is available, provide it via context for reactive queries.
  if (!db) {
    return <>{children}</>;
  }

  return (
    <PowerSyncContext.Provider value={db as any}>
      {children}
    </PowerSyncContext.Provider>
  );
}
