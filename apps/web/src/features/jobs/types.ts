import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export type JobSummary = S["JobSummary"];
export type JobStatus = JobSummary["status"];
export type JobOut = S["JobOut"];
export type JobDetail = S["JobDetail"];
export type JobDescription = S["JobDescription"];
export type JobAdd = S["JobAdd"];
export type JobAddOut = S["JobAddOut"];
export type JobList = S["JobList"];
export type JobPatch = S["JobPatch"];
export type Must = S["Must"];
export type RunDetail = S["RunDetail"];
export type RunStatus = RunDetail["status"];
export type PendingQuestion = S["PendingQuestion"];
export type IterationOut = S["IterationOut"];
export type Answer = S["Answer"];
export type EventOut = S["EventOut"];

export type JobFilters = {
  status?: JobStatus;
  min_score?: number;
  city?: string;
  q?: string;
  sort: "score" | "created_at";
};

export const ACTIVE_RUN: readonly RunStatus[] = [
  "queued",
  "running",
  "waiting_for_user",
];
export const isActiveRun = (s: string | undefined | null) =>
  ACTIVE_RUN.includes(s as RunStatus);
