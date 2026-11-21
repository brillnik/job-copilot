import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { ToastProvider } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import type { JobDetail, JobSummary, RunDetail } from "./types";

export function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <ToastProvider>{ui}</ToastProvider>
      </QueryClientProvider>,
    ),
  };
}

export const apiError = (
  status: number,
  code: string,
  details?: Record<string, unknown>,
) => new ApiError({ status, code, message: code, details });

export function job(over: Partial<JobSummary> = {}): JobSummary {
  return {
    id: "j1",
    company: "Acme",
    title: "Frontend Engineer",
    location: "Bengaluru",
    ctc_lpa_min: 30,
    ctc_lpa_max: 40,
    score: 82,
    musts_summary: "4 of 6",
    status: "new",
    red_flags: [],
    created_at: "2026-01-05T10:00:00Z",
    ...over,
  };
}

export function detail(over: Partial<JobDetail> = {}): JobDetail {
  return {
    job: {
      id: "j1",
      source: "url",
      url: "https://acme.example/jobs/1",
      status: "new",
      status_reason: null,
      company: "Acme",
      title: "Frontend Engineer",
      score: 82,
      red_flags: [],
      max_pages_override: null,
      created_at: "2026-01-05T10:00:00Z",
      updated_at: "2026-01-05T10:00:00Z",
    },
    jd: {
      title: "Frontend Engineer",
      company: "Acme",
      location: "Bengaluru",
      work_mode: "hybrid",
      experience_years_min: 3,
      experience_years_max: 6,
      ctc_lpa_min: 30,
      ctc_lpa_max: 40,
      seniority: "Senior",
      must_have: ["React", "TypeScript"],
      nice_to_have: ["GraphQL"],
      responsibilities: ["Build the web app"],
      keywords: ["frontend"],
      red_flags: [],
      requested_resume_pages: null,
      source_url: null,
    },
    score_breakdown: null,
    musts: [
      {
        skill: "React",
        status: "have",
        evidence_bullet_id: "abcdef0123456789",
      },
      { skill: "GraphQL", status: "ask", evidence_bullet_id: null },
      { skill: "Go", status: "missing", evidence_bullet_id: null },
      { skill: "Rust", status: "unknown", evidence_bullet_id: null },
    ],
    latest_run: null,
    ...over,
  };
}

export function run(over: Partial<RunDetail> = {}): RunDetail {
  return {
    id: "r1",
    job_id: "j1",
    company: "Acme",
    title: "Frontend Engineer",
    status: "running",
    status_reason: null,
    flagged: false,
    current_step: "plan",
    iteration: 1,
    profile_version: 1,
    max_pages: null,
    pending_questions: [],
    created_at: "2026-01-05T10:00:00Z",
    updated_at: "2026-01-05T10:00:00Z",
    draft_rev: null,
    edited: false,
    summary: null,
    skills_order: [],
    cover_note: null,
    bullets: [],
    violations: [],
    coverage: null,
    pages: null,
    iterations: [],
    has_pdf: false,
    ...over,
  };
}
