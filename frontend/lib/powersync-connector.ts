import {
  type AbstractPowerSyncDatabase,
  type PowerSyncBackendConnector,
} from "@powersync/web";
import { supabase } from "./supabase";

const POWERSYNC_URL = process.env.NEXT_PUBLIC_POWERSYNC_URL!;

export class SupabaseConnector implements PowerSyncBackendConnector {
  async fetchCredentials() {
    const {
      data: { session },
    } = await supabase.auth.getSession();

    if (!session) {
      console.warn("[PowerSync] No Supabase session — cannot fetch credentials");
      return null;
    }

    return {
      endpoint: POWERSYNC_URL,
      token: session.access_token,
      expiresAt: session.expires_at
        ? new Date(session.expires_at * 1000)
        : undefined,
    };
  }

  async uploadData(_database: AbstractPowerSyncDatabase): Promise<void> {
    // No-op: all writes go through FastAPI HTTP, not the PowerSync upload queue.
  }
}
