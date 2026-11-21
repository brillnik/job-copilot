import type { Page, Route } from "@playwright/test";
import { stubApi } from "./stubs";

const json = (body: unknown, status = 200, headers: Record<string, string> = {}) => ({
  status,
  contentType: "application/json",
  headers,
  body: JSON.stringify(body),
});
const err = (status: number, code: string, details?: unknown) =>
  json({ code, message: `stub ${code}`, details }, status);

export const run = (over: Record<string, unknown> = {}) => ({
  id: "run1",
  job_id: "job1",
  company: "Acme",
  title: "Frontend Engineer",
  status: "in_review",
  status_reason: null,
  flagged: true,
  current_step: null,
  iteration: 1,
  profile_version: 1,
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
      revert_reason: "The rewrite introduced a number that is not in your profile",
    },
  ],
  violations: [
    { code: "unsupported_skill", field: "skills_order", source_id: null, term: "GraphQL", message: "GraphQL is not in your profile", blocked: false },
  ],
  coverage: { covered: ["React", "TypeScript"], missing: ["GraphQL"], pct: 0.67 },
  pages: { count: 2, last_page_fill: 0.4 },
  iterations: [],
  has_pdf: true,
  ...over,
});

export type ReviewState = {
  puts: Array<{ ifMatch: string | null; body: Record<string, unknown> }>;
  approves: number;
  rejects: Array<Record<string, unknown>>;
  regenerates: Array<Record<string, unknown>>;
};

/** /review queue + /review/run1 detail. Summary edits containing "10" are refused by the fact check. */
export async function stubReview(page: Page): Promise<ReviewState> {
  await stubApi(page, { reviewCount: 0 });
  const state: ReviewState = { puts: [], approves: 0, rejects: [], regenerates: [] };
  let current = run();
  await page.route("**/api/runs?**", (r) =>
    r.fulfill(
      json({
        items: [
          {
            id: "run1",
            job_id: "job1",
            company: "Acme",
            title: "Frontend Engineer",
            status: "in_review",
            flagged: true,
            score: 82,
            coverage: "5/6",
            pages: 2,
            created_at: "2026-01-01T00:00:00Z",
            top_changes: ["Led with design-system work"],
          },
        ],
        next_cursor: null,
      }),
    ),
  );
  await page.route("**/api/runs/run1", (r) => r.fulfill(json(current, 200, { etag: `"${current.draft_rev}"` })));
  await page.route("**/api/runs/run1/pdf**", (r) =>
    r.fulfill({ status: 200, contentType: "application/pdf", body: "%PDF-1.4\n%%EOF" }),
  );
  await page.route("**/api/runs/run1/draft", async (r: Route) => {
    const body = r.request().postDataJSON() as Record<string, unknown>;
    state.puts.push({ ifMatch: r.request().headers()["if-match"] ?? null, body });
    const violations: unknown[] = [];
    const applied: string[] = [];
    const next = { ...current };
    if (typeof body.summary === "string") {
      if (/\b10\b/.test(body.summary)) {
        violations.push({ code: "invented_number", field: "summary", source_id: null, term: "10", message: "10 is not in your profile", blocked: true });
      } else {
        next.summary = body.summary;
        applied.push("summary");
      }
    }
    if (typeof body.cover_note === "string") {
      next.cover_note = body.cover_note;
      applied.push("cover_note");
    }
    if (applied.length) {
      next.draft_rev = current.draft_rev + 1;
      next.edited = true;
      next.has_pdf = true;
    }
    current = next;
    await r.fulfill(json({ run: current, applied, violations }));
  });
  await page.route("**/api/runs/run1/approve", (r) => {
    state.approves += 1;
    current = { ...current, status: "approved" };
    return r.fulfill(json({ approval_id: "a1", file_name: "frontend-engineer.pdf" }));
  });
  await page.route("**/api/runs/run1/reject", (r) => {
    state.rejects.push(r.request().postDataJSON());
    return r.fulfill(json({ run_id: "run1", status: "rejected" }));
  });
  await page.route("**/api/runs/run1/regenerate", (r) => {
    state.regenerates.push(r.request().postDataJSON());
    return r.fulfill(json({ run_id: "run2" }, 202));
  });
  return state;
}

export type TrackerState = { patches: Array<{ id: string; ifMatch: string | null; body: Record<string, unknown> }>; failNext: boolean };

const card = (over: Record<string, unknown>) => ({
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

export async function stubTracker(page: Page): Promise<TrackerState> {
  await stubApi(page);
  const state: TrackerState = { patches: [], failNext: false };
  const cols: Record<string, ReturnType<typeof card>[]> = {
    approved: [card({ id: "c0", title: "Backend Engineer", company: "Globex", column: "approved", rev: 1, notes_preview: null, applied_at: null, score: 74 })],
    applied: [card({})],
    response: [],
    interview: [],
    offer: [],
    rejected: [],
  };
  const stats = () => ({
    applied_this_week: 3,
    response_rate: 0.25,
    avg_match_score: 78,
    counts: Object.fromEntries(Object.entries(cols).map(([k, v]) => [k, v.length])),
  });
  await page.route("**/api/tracker", (r) => r.fulfill(json({ columns: cols, stats: stats() })));
  await page.route("**/api/tracker/*", async (r) => {
    const id = r.request().url().split("/").pop()!;
    const body = r.request().postDataJSON() as { column?: string; notes?: string };
    state.patches.push({ id, ifMatch: r.request().headers()["if-match"] ?? null, body });
    if (state.failNext) {
      state.failNext = false;
      return r.fulfill(err(409, "stale_write", { rev: 9 }));
    }
    let found: ReturnType<typeof card> | undefined;
    for (const k of Object.keys(cols)) {
      const i = cols[k].findIndex((c) => c.id === id);
      if (i >= 0) found = cols[k].splice(i, 1)[0];
    }
    const next = { ...found!, rev: found!.rev + 1, column: body.column ?? found!.column, notes_preview: body.notes ?? found!.notes_preview };
    cols[next.column].push(next);
    return r.fulfill(json({ ...next, notes: body.notes ?? found!.notes_preview, position: 1, history: [] }));
  });
  return state;
}

export type SettingsState = {
  puts: Array<{ ifMatch: string | null; body: Record<string, unknown> }>;
  deletes: number;
  reauth: boolean;
  revoked: string[];
  exports: number;
};

export async function stubSettings(page: Page, opts: { reauth?: boolean } = {}): Promise<SettingsState> {
  const state: SettingsState = { puts: [], deletes: 0, reauth: opts.reauth ?? true, revoked: [], exports: 0 };
  const base = await stubApi(page);
  let rev = 1;
  const prefs = {
    target_roles: ["Frontend Engineer"],
    cities: ["Bengaluru"],
    current_ctc_lpa: 18,
    expected_ctc_lpa: 28,
    notice_days: 30,
    default_length: "auto",
    template: "classic",
    daily_cap: 5,
    coverage_target: 0.8,
    theme: "system",
  };
  let cur = { ...prefs };
  await page.route("**/api/settings", async (r) => {
    if (r.request().method() === "PUT") {
      const body = r.request().postDataJSON() as typeof prefs;
      state.puts.push({ ifMatch: r.request().headers()["if-match"] ?? null, body });
      cur = body;
      rev += 1;
      base.rev = rev;
    }
    return r.fulfill(
      json(
        { preferences: cur, configured: true, rev, runs_used_today: 2, daily_cap: cur.daily_cap, cap_resets_at: "2026-01-02T00:00:00Z" },
        200,
        { etag: `"${rev}"` },
      ),
    );
  });
  let revoked = false;
  await page.route("**/api/extension/tokens", (r) =>
    r.fulfill(
      json([
        { id: "t1", device_name: "Chrome on Mac", created_at: "2026-01-01T00:00:00Z", last_used_at: null, revoked_at: revoked ? "2026-01-03T00:00:00Z" : null },
      ]),
    ),
  );
  await page.route("**/api/extension/tokens/t1", (r) => {
    state.revoked.push("t1");
    revoked = true;
    return r.fulfill({ status: 204 });
  });
  let polls = 0;
  await page.route("**/api/me/export", (r) => {
    state.exports += 1;
    return r.fulfill(json({ export_id: "e1" }, 202));
  });
  await page.route("**/api/me/export/e1", (r) => {
    polls += 1;
    const ready = polls > 1;
    return r.fulfill(
      json({
        export_id: "e1",
        status: ready ? "ready" : "running",
        created_at: "2026-01-01T00:00:00Z",
        expires_at: ready ? "2026-01-08T00:00:00Z" : null,
        download_url: ready ? "http://api.invalid/files/abc.def" : null,
      }),
    );
  });
  await page.route("**/api/me", (r) => {
    if (r.request().method() === "DELETE") {
      state.deletes += 1;
      return state.reauth ? r.fulfill(err(401, "reauth_required")) : r.fulfill(json({ status: "deleting" }, 202));
    }
    return r.fulfill(
      json({
        id: "00000000-0000-4000-8000-000000000001",
        email: "test@example.com",
        name: "Test User",
        auth_providers: ["google"],
        consent: { policy_version: "2026-01", at: "2026-01-01T00:00:00Z" },
        created_at: "2026-01-01T00:00:00Z",
        plan: "free",
      }),
    );
  });
  return state;
}
