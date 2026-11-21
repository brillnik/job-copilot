import type { Board, TrackerCard } from "./api";

export const cardFixture = (over: Partial<TrackerCard> = {}): TrackerCard => ({
  id: "c1",
  job_id: "j1",
  company: "Acme",
  title: "Frontend Engineer",
  score: 82,
  column: "applied",
  applied_at: "2026-01-01T00:00:00Z",
  notes_preview: "Spoke to recruiter",
  updated_at: "2026-01-02T00:00:00Z",
  rev: 2,
  ...over,
});

export const boardFixture = (): Board => ({
  columns: {
    approved: [
      cardFixture({
        id: "c0",
        title: "Backend Engineer",
        company: "Globex",
        column: "approved",
        rev: 1,
        notes_preview: null,
        applied_at: null,
        score: 74,
      }),
    ],
    applied: [cardFixture()],
    response: [],
    interview: [],
    offer: [],
    rejected: [],
  },
  stats: {
    applied_this_week: 3,
    response_rate: 0.25,
    avg_match_score: 78,
    counts: {
      approved: 1,
      applied: 1,
      response: 0,
      interview: 0,
      offer: 0,
      rejected: 0,
    },
  },
});
