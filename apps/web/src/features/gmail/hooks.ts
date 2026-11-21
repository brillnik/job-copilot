"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";
import type { components } from "@/lib/api/schema";

export type GmailStatus = components["schemas"]["GmailStatus"];
export type Suggestion = components["schemas"]["Suggestion"];

export const gmailKey = ["gmail", "status"] as const;
export const suggestionsKey = ["gmail", "suggestions"] as const;

export function useGmailStatus() {
  return useQuery({
    queryKey: gmailKey,
    queryFn: () => unwrap(api.GET("/integrations/gmail")),
  });
}

export function useSuggestions(enabled: boolean) {
  return useQuery({
    queryKey: suggestionsKey,
    enabled,
    queryFn: () => unwrap(api.GET("/integrations/gmail/suggestions")),
  });
}

/** Resolve a suggestion. Either way the status (pending count) and list are stale. */
export function useResolveSuggestion(kind: "accept" | "dismiss") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      kind === "accept"
        ? unwrap(
            api.POST("/integrations/gmail/suggestions/{suggestion_id}/accept", {
              params: { path: { suggestion_id: id } },
            }),
          )
        : unwrap(
            api.POST(
              "/integrations/gmail/suggestions/{suggestion_id}/dismiss",
              {
                params: { path: { suggestion_id: id } },
              },
            ),
          ),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: suggestionsKey });
      void qc.invalidateQueries({ queryKey: gmailKey });
      void qc.invalidateQueries({ queryKey: ["tracker"] });
    },
  });
}

export function useDisconnectGmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/integrations/gmail")),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["gmail"] });
    },
  });
}

/** Fetch the Google consent URL; the caller redirects the whole browser to it. */
export function useConnectGmail() {
  return useMutation({
    mutationFn: async () =>
      (await unwrap(api.GET("/integrations/gmail/connect"))).url,
  });
}
