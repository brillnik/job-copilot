"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { isApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { unwrap } from "@/lib/api/unwrap";

export type ProfileOut = components["schemas"]["ProfileOut"];
export type ProfileData = components["schemas"]["ProfileData"];
export type Bullet = components["schemas"]["Bullet"];

export const approvedKey = ["profile", "approved"] as const;
export const draftKey = ["profile", "draft"] as const;

/** GET /profile and /profile/draft answer 404 when there is none: that is `null`, not an error. */
async function orNull<T>(p: Promise<T>): Promise<T | null> {
  try {
    return await p;
  } catch (e) {
    if (isApiError(e) && e.status === 404) return null;
    throw e;
  }
}

export const fetchApproved = () => orNull(unwrap(api.GET("/profile")));
export const fetchDraft = () => orNull(unwrap(api.GET("/profile/draft")));

export function useApprovedProfile() {
  return useQuery({ queryKey: approvedKey, queryFn: fetchApproved });
}

export function useDraftProfile(enabled = true) {
  return useQuery({ queryKey: draftKey, queryFn: fetchDraft, enabled });
}

/**
 * POST /profile/upload is one synchronous multipart request that returns the
 * draft once extraction finishes (it can take minutes on a local model).
 */
export function uploadResume(file: File, signal?: AbortSignal) {
  return unwrap(
    api.POST("/profile/upload", {
      // The generated type is `string`; the real body is built below.
      body: { file: file as unknown as string },
      bodySerializer: () => {
        const fd = new FormData();
        fd.append("file", file);
        return fd;
      },
      signal,
    }),
  );
}

export const putDraft = (data: ProfileData) =>
  unwrap(api.PUT("/profile/draft", { body: data }));

export const approveDraft = () => unwrap(api.POST("/profile/approve"));
