"use client";

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";
import { getJob, getRun, listJobs } from "./api";
import { isActiveRun, type JobFilters, type JobStatus } from "./types";

export const jobsKey = ["jobs"] as const;
export const jobKey = (id: string) => ["jobs", "detail", id] as const;
export const runKey = (id: string) => ["runs", "detail", id] as const;

export function useJobList(filters: JobFilters) {
  return useInfiniteQuery({
    queryKey: ["jobs", "list", filters],
    queryFn: ({ pageParam }) => listJobs(filters, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useJob(id: string, enabled = true) {
  return useQuery({
    queryKey: jobKey(id),
    queryFn: () => getJob(id),
    enabled,
  });
}

/** The run is refreshed by the SSE stream; this only reads the current state. */
export function useRun(id: string | null | undefined) {
  return useQuery({
    queryKey: runKey(id ?? "none"),
    queryFn: () => getRun(id as string),
    enabled: Boolean(id),
    // Safety net while a run is active in case the stream is unavailable.
    refetchInterval: (q) =>
      isActiveRun(q.state.data?.status) ? 15_000 : false,
  });
}

/**
 * Bullet text by id from the approved profile, for evidence tooltips. A missing
 * profile (404) is not an error here: the UI then shows the bare id.
 */
export function useBulletTexts() {
  return useQuery({
    queryKey: ["profile", "bullet-texts"],
    queryFn: async () => {
      const map = new Map<string, string>();
      try {
        const profile = await unwrap(api.GET("/profile"));
        for (const e of profile.data.experience)
          for (const b of e.bullets) if (b.id) map.set(b.id, b.text);
        for (const p of profile.data.projects)
          for (const b of p.bullets) if (b.id) map.set(b.id, b.text);
      } catch {
        /* no approved profile yet */
      }
      return map;
    },
    staleTime: 60_000,
  });
}

export const jobIsTailorable = (s: JobStatus) =>
  s !== "processing" &&
  s !== "needs_paste" &&
  s !== "failed" &&
  s !== "archived";
