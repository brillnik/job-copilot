"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { ApiError, toApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { unwrap } from "@/lib/api/unwrap";
import { reviewCountKey } from "@/hooks/use-review-count";

export type RunDetail = components["schemas"]["RunDetail"];
export type RunSummary = components["schemas"]["RunSummary"];
export type Violation = components["schemas"]["Violation"];
export type BulletReview = components["schemas"]["BulletReview"];
export type DraftEdit = components["schemas"]["DraftEdit"];
export type DraftEditOut = components["schemas"]["DraftEditOut"];
export type RejectReason = components["schemas"]["RejectIn"]["reasons"] extends
  (infer R)[] | undefined
  ? R
  : never;
export type MaxPages = 1 | 2 | 3;

export const runKey = (id: string) => ["runs", "detail", id] as const;
export const queueKey = ["runs", "list", "in_review"] as const;

const IN_PROGRESS = ["queued", "running", "waiting_for_user"];

/** One run with its draft. Polls while the run is progressing or the PDF re-renders. */
export function useRun(id: string) {
  return useQuery({
    queryKey: runKey(id),
    queryFn: () =>
      unwrap(api.GET("/runs/{run_id}", { params: { path: { run_id: id } } })),
    refetchInterval: (q) => {
      const r = q.state.data;
      if (!r) return false;
      if (IN_PROGRESS.includes(r.status)) return 3000;
      if (r.status === "in_review" && !r.has_pdf) return 2500;
      return false;
    },
    retry: (count, e) =>
      count < 1 &&
      !(e instanceof ApiError && e.status >= 400 && e.status < 500),
  });
}

const PAGE = 20;
export function useReviewQueue() {
  return useInfiniteQuery({
    queryKey: queueKey,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/runs", {
          params: {
            query: { status: "in_review", limit: PAGE, cursor: pageParam },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

function useInvalidateRuns() {
  const qc = useQueryClient();
  return (id?: string) => {
    void qc.invalidateQueries({ queryKey: queueKey });
    void qc.invalidateQueries({ queryKey: reviewCountKey });
    if (id) void qc.invalidateQueries({ queryKey: runKey(id) });
  };
}

export function useApprove() {
  const refresh = useInvalidateRuns();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/runs/{run_id}/approve", {
          params: { path: { run_id: id } },
        }),
      ),
    onSuccess: (_d, id) => refresh(id),
    onError: (e, id) => {
      // The run may have moved on (stale list): refresh so the UI tells the truth.
      if (e instanceof ApiError && e.code === "invalid_state") refresh(id);
    },
  });
}

export function useReject() {
  const refresh = useInvalidateRuns();
  return useMutation({
    mutationFn: (v: { id: string; reasons: RejectReason[]; note?: string }) =>
      unwrap(
        api.POST("/runs/{run_id}/reject", {
          params: { path: { run_id: v.id } },
          body: {
            reasons: v.reasons,
            note: v.note?.trim() ? v.note.trim() : null,
          },
        }),
      ),
    onSuccess: (_d, v) => refresh(v.id),
  });
}

export function useRegenerate() {
  const refresh = useInvalidateRuns();
  return useMutation({
    mutationFn: (v: {
      id: string;
      maxPages?: MaxPages | null;
      confirmRedFlags?: boolean;
    }) =>
      unwrap(
        api.POST("/runs/{run_id}/regenerate", {
          params: { path: { run_id: v.id } },
          body: {
            max_pages: v.maxPages ?? null,
            guidance_from_rejection: true,
            confirm_red_flags: v.confirmRedFlags ?? false,
          },
        }),
      ),
    onSuccess: (_d, v) => refresh(v.id),
  });
}

/** PUT /runs/{id}/draft guarded by If-Match = the draft revision. */
export async function putDraft(
  id: string,
  rev: number | null,
  body: DraftEdit,
): Promise<DraftEditOut> {
  const { data, error, response } = await api.PUT("/runs/{run_id}/draft", {
    params: {
      path: { run_id: id },
      header: rev === null ? {} : { "if-match": `"${rev}"` },
    },
    body,
  });
  if (data) return data;
  throw toApiError(error, response.status);
}

/** Same-origin PDF URL (the proxy follows the signed redirect server-side). */
export function pdfHref(
  id: string,
  which: "latest" | "approved",
  rev?: number | null,
) {
  const v = rev == null ? "" : `&v=${rev}`;
  return `/api/runs/${encodeURIComponent(id)}/pdf?draft=${which}${v}`;
}

const MESSAGES: Record<string, string> = {
  pdf_not_ready:
    "The PDF is still being rendered. Give it a few seconds, then approve.",
  invalid_state: "This draft is no longer waiting for review.",
  stale_write: "This draft changed since you opened it.",
  no_profile: "Finish your profile before generating resumes.",
  jd_not_ready: "The job description is still being read. Try again shortly.",
  run_in_progress: "A resume for this job is already being prepared.",
  no_draft: "This run has no draft yet.",
};

export function reviewErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "daily_cap") {
      const d = e.details as { used?: number; cap?: number } | null | undefined;
      return d && typeof d.used === "number" && typeof d.cap === "number"
        ? `You've used ${d.used} of ${d.cap} resumes today. The limit resets tomorrow.`
        : e.message;
    }
    return MESSAGES[e.code] ?? e.message;
  }
  return "Something went wrong. Check your connection and try again.";
}

/** Job names for headings, never undefined. */
export function runName(r: { company: string | null; title: string | null }) {
  return [r.title, r.company].filter(Boolean).join(" at ") || "Untitled job";
}

export function coveragePctLabel(pct: number) {
  return `${Math.round(pct * 100)}%`;
}
