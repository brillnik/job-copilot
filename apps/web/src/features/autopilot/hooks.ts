"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";
import type { components } from "@/lib/api/schema";

export type Autopilot = components["schemas"]["AutopilotOut"];
export type AutopilotPut = components["schemas"]["AutopilotPut"];
export type Digest = components["schemas"]["DigestOut"];
export type DigestItem = components["schemas"]["DigestItem"];

export const autopilotKey = ["autopilot"] as const;

export function useAutopilot() {
  return useQuery({
    queryKey: autopilotKey,
    queryFn: () => unwrap(api.GET("/autopilot")),
  });
}

export function useSaveAutopilot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AutopilotPut) => unwrap(api.PUT("/autopilot", { body })),
    onSuccess: (data) => qc.setQueryData(autopilotKey, data),
  });
}

/** `date` is YYYY-MM-DD; undefined means "today" (decided by the server). */
export function useDigest(date: string | undefined) {
  return useQuery({
    queryKey: ["autopilot", "digest", date ?? "today"],
    queryFn: () =>
      unwrap(api.GET("/autopilot/digest", { params: { query: { date } } })),
  });
}
