"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { ApiError, toApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { unwrap } from "@/lib/api/unwrap";
import {
  type Preferences,
  type SettingsOut,
  settingsKey,
} from "@/hooks/use-settings";

export type ExportOut = components["schemas"]["ExportOut"];
export type DeviceToken = components["schemas"]["TokenOut"];

/** Full replace with If-Match = the revision the form was based on. */
export async function savePreferences(
  body: Preferences,
  rev: number,
): Promise<SettingsOut> {
  const { data, error, response } = await api.PUT("/settings", {
    body,
    params: { header: { "if-match": `"${rev}"` } },
  });
  if (data) return data;
  throw toApiError(error, response.status);
}

export function useSavePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { body: Preferences; rev: number }) =>
      savePreferences(v.body, v.rev),
    onSuccess: (data) => qc.setQueryData(settingsKey, data),
  });
}

// ---- data export -------------------------------------------------------

export const exportKey = (id: string) => ["export", id] as const;

export function useRequestExport() {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/me/export")),
  });
}

/** Polls while the export is queued or running. */
export function useExport(id: string | null) {
  return useQuery({
    queryKey: exportKey(id ?? "none"),
    enabled: id !== null,
    queryFn: () =>
      unwrap(
        api.GET("/me/export/{export_id}", {
          params: { path: { export_id: id! } },
        }),
      ),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "running" ? 2000 : false;
    },
  });
}

/**
 * The signed download link points at the API origin. Serve it through the same-origin
 * proxy (the token in the path is the credential), and never log it.
 */
export function downloadHref(url: string): string {
  try {
    const u = new URL(url, "http://localhost");
    return u.pathname.startsWith("/files/") ? `/api${u.pathname}` : url;
  } catch {
    return url;
  }
}

// ---- extension devices ----------------------------------------------------

export const devicesKey = ["extension", "tokens"] as const;

export function useDevices() {
  return useQuery({
    queryKey: devicesKey,
    queryFn: () => unwrap(api.GET("/extension/tokens")),
  });
}

export function useRevokeDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/extension/tokens/{token_id}", {
          params: { path: { token_id: id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: devicesKey }),
  });
}

// ---- account ---------------------------------------------------------------

export async function deleteAccount(): Promise<void> {
  const { error, response } = await api.DELETE("/me", {
    body: { confirm: "DELETE" },
  });
  if (!response.ok) throw toApiError(error, response.status);
}

export async function logoutEverywhere(): Promise<void> {
  const { error, response } = await api.POST("/auth/logout-all");
  if (!response.ok) throw toApiError(error, response.status);
}

export const isReauth = (e: unknown) =>
  e instanceof ApiError && e.code === "reauth_required";

/** Auth0 re-login that proves a fresh sign-in (max_age=0), then returns to settings. */
export function reauthUrl() {
  const q = new URLSearchParams({
    returnTo: "/settings?delete=1",
    prompt: "login",
    max_age: "0",
  });
  return `/auth/login?${q}`;
}
