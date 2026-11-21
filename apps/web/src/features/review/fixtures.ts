import type { RunDetail, RunSummary } from "./api";

export const runFixture = (over: Partial<RunDetail> = {}): RunDetail => ({
  id: "run1",
  job_id: "job1",
  company: "Acme",
  title: "Frontend Engineer",
  status: "in_review",
  status_reason: null,
  flagged: false,
  current_step: null,
  iteration: 1,
  profile_version: 2,
  max_pages: 2,
  pending_questions: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  draft_rev: 3,
  edited: false,
  summary: "Frontend engineer with 6 years building design systems.",
  skills_order: ["React", "TypeScript"],
  cover_note: "Hello Acme team.",
  bullets: [
    {
      source_id: "exp.0.b1",
      source_text: "Built a design system used by 12 teams",
      tailored_text: "Built a React design system used by 12 teams",
      diff: [
        { op: "same", text: "Built a " },
        { op: "add", text: "React " },
        { op: "same", text: "design system used by 12 teams" },
      ],
      reverted: false,
      revert_reason: null,
    },
    {
      source_id: "exp.0.b2",
      source_text: "Cut build times by 40%",
      tailored_text: "Cut build times by 40%",
      diff: [{ op: "same", text: "Cut build times by 40%" }],
      reverted: true,
      revert_reason:
        "The rewrite introduced a number that is not in your profile",
    },
  ],
  violations: [],
  coverage: {
    covered: ["React", "TypeScript"],
    missing: ["GraphQL"],
    pct: 0.67,
  },
  pages: { count: 2, last_page_fill: 0.4 },
  iterations: [
    { iteration: 1, outcome: "iteration 1: coverage 67%, 0 violation(s)" },
  ],
  has_pdf: true,
  ...over,
});

export const summaryFixture = (over: Partial<RunSummary> = {}): RunSummary => ({
  id: "run1",
  job_id: "job1",
  company: "Acme",
  title: "Frontend Engineer",
  status: "in_review",
  flagged: false,
  score: 82,
  coverage: "5/6",
  pages: 2,
  created_at: "2026-01-01T00:00:00Z",
  top_changes: ["Led with design-system work", "Added React keywords"],
  ...over,
});
