"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useEffectEvent } from "react";
import { reviewCountKey } from "@/hooks/use-review-count";
import { settingsKey } from "@/hooks/use-settings";
import { getEvents } from "./api";

// GET /events is the only per-user live source (there is no per-user SSE), so
// this polls it with the returned `last_id`: every 3 s while the tab is
// visible, backing off to 15 s when nothing happens, paused while hidden.
// The cursor lives at module level so remounting a screen never replays history.
let lastId = 0;
const MIN_MS = 3000;
const MAX_MS = 15000;

export function resetJobEventsCursor() {
  lastId = 0;
}

export function nextDelay(current: number, gotEvents: boolean) {
  return gotEvents ? MIN_MS : Math.min(MAX_MS, Math.round(current * 1.5));
}

/** Returns the count of updates seen since mount via `onUpdate` (for announcements). */
export function useJobEvents(onUpdate?: (types: string[]) => void) {
  const qc = useQueryClient();
  const notify = useEffectEvent((types: string[]) => onUpdate?.(types));

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = MIN_MS;

    async function poll() {
      if (stopped) return;
      if (document.hidden) {
        timer = setTimeout(poll, MAX_MS); // visibilitychange polls right away
        return;
      }
      let got = false;
      try {
        for (;;) {
          const page = await getEvents(lastId);
          lastId = page.last_id;
          if (page.events.length === 0) break;
          got = true;
          const types = page.events.map((e) => e.type);
          void qc.invalidateQueries({ queryKey: ["jobs"] });
          if (types.some((t) => t.startsWith("run_"))) {
            void qc.invalidateQueries({ queryKey: ["runs"] });
            void qc.invalidateQueries({ queryKey: settingsKey });
            void qc.invalidateQueries({ queryKey: reviewCountKey });
          }
          notify(types);
          if (page.events.length < 200) break;
        }
      } catch {
        // Offline or a transient error: keep the screen as is and retry later.
        got = false;
      }
      delay = nextDelay(delay, got);
      if (!stopped) timer = setTimeout(poll, delay);
    }

    const onVisible = () => {
      if (!document.hidden) {
        clearTimeout(timer);
        delay = MIN_MS;
        void poll();
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [qc]);
}
