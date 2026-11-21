import { api } from "@/lib/api/browser";
import { toApiError } from "@/lib/api/errors";
import { unwrap } from "@/lib/api/unwrap";
import type { Answer, JobAdd, JobFilters, JobPatch } from "./types";

export const PAGE_SIZE = 20;

export function listJobs(filters: JobFilters, cursor?: string) {
  return unwrap(
    api.GET("/jobs", {
      params: { query: { ...filters, cursor, limit: PAGE_SIZE } },
    }),
  );
}

export function getJob(id: string) {
  return unwrap(
    api.GET("/jobs/{job_id}", { params: { path: { job_id: id } } }),
  );
}

export function patchJob(id: string, body: JobPatch) {
  return unwrap(
    api.PATCH("/jobs/{job_id}", { params: { path: { job_id: id } }, body }),
  );
}

/** POST /jobs answers 202 (new) or 200 (duplicate of an existing job). */
export async function addJob(body: JobAdd) {
  const { data, error, response } = await api.POST("/jobs", { body });
  if (!data) throw toApiError(error, response.status);
  return { ...data, duplicate: data.duplicate || response.status === 200 };
}

/** Upload a PNG/JPEG first; the returned id goes into POST /jobs. */
export async function uploadImage(file: File) {
  const { data, error, response } = await api.POST("/jobs/images", {
    body: { file: "" },
    bodySerializer: () => {
      const form = new FormData();
      form.append("file", file);
      return form;
    },
  });
  if (!data) throw toApiError(error, response.status);
  return data.image_id;
}

export async function tailorJob(id: string, confirmRedFlags = false) {
  const data = await unwrap(
    api.POST("/jobs/{job_id}/tailor", {
      params: { path: { job_id: id } },
      body: { confirm_red_flags: confirmRedFlags },
    }),
  );
  return data.run_id;
}

export function getRun(id: string) {
  return unwrap(
    api.GET("/runs/{run_id}", { params: { path: { run_id: id } } }),
  );
}

export function answerRun(id: string, answers: Answer[]) {
  return unwrap(
    api.POST("/runs/{run_id}/answer", {
      params: { path: { run_id: id } },
      body: { answers },
    }),
  );
}

export function cancelRun(id: string) {
  return unwrap(
    api.POST("/runs/{run_id}/cancel", { params: { path: { run_id: id } } }),
  );
}

export function getEvents(after: number) {
  return unwrap(
    api.GET("/events", { params: { query: { after, limit: 200 } } }),
  );
}
