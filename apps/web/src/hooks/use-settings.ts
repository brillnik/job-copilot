"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { toApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { unwrapWithEtag } from "@/lib/api/unwrap";
import type { Theme } from "@/lib/theme";

export type SettingsOut = components["schemas"]["SettingsOut"];
export type Preferences = components["schemas"]["Preferences"];
export const settingsKey = ["settings"] as const;

export function fetchSettings() {
  return unwrapWithEtag(api.GET("/settings"));
}

function etagFor(s: { etag: string | null; data: SettingsOut }) {
  return s.etag ?? `"${s.data.rev}"`;
}

/**
 * PUT /settings is a full replace guarded by If-Match, so the update is
 * read-modify-write: fetch the latest, merge the patch, send with its ETag.
 * A stale write (409) is retried once against a fresh read.
 */
export async function updatePreferences(
  patch: Partial<Preferences>,
): Promise<SettingsOut> {
  for (let attempt = 0; ; attempt++) {
    const current = await fetchSettings();
    const body: Preferences = { ...current.data.preferences, ...patch };
    const { data, error, response } = await api.PUT("/settings", {
      body,
      params: { header: { "if-match": etagFor(current) } },
    });
    if (data) return data;
    const err = toApiError(error, response.status);
    if (err.isStaleWrite && attempt === 0) continue;
    throw err;
  }
}

export function useSettings() {
  return useQuery({
    queryKey: settingsKey,
    queryFn: async () => (await fetchSettings()).data,
  });
}

export function useSaveTheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (theme: Theme) => updatePreferences({ theme }),
    onSuccess: (data) => qc.setQueryData(settingsKey, data),
  });
}
