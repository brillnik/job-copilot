import type { Page } from "@playwright/test";

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

export type StubState = {
  puts: Array<{ ifMatch: string | null; body: typeof prefs }>;
  rev: number;
  theme: string;
};

/** Stub the Next /api proxy that the browser talks to (/me, /runs, /settings). */
export async function stubApi(
  page: Page,
  opts: { reviewCount?: number; theme?: string } = {},
): Promise<StubState> {
  const state: StubState = { puts: [], rev: 1, theme: opts.theme ?? "system" };
  const json = (body: unknown, headers: Record<string, string> = {}) => ({
    status: 200,
    contentType: "application/json",
    headers,
    body: JSON.stringify(body),
  });

  await page.route("**/api/me", (r) =>
    r.fulfill(
      json({
        id: "00000000-0000-4000-8000-000000000001",
        email: "test@example.com",
        name: "Test User",
        auth_providers: ["google"],
        consent: { policy_version: "2026-01", at: "2026-01-01T00:00:00Z" },
        created_at: "2026-01-01T00:00:00Z",
        plan: "free",
      }),
    ),
  );
  // A set-up account: the app shell's setup gate needs an approved profile.
  await page.route("**/api/profile", (r) =>
    r.fulfill(
      json({
        id: "p-approved",
        status: "approved",
        version: 1,
        resume_id: null,
        data: {
          contact: { name: "Test User", email: "test@example.com", links: [] },
          experience: [],
          projects: [],
          education: [],
          skills: [],
        },
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
        approved_at: "2026-01-01T00:00:00Z",
      }),
    ),
  );
  // Inbox (Phase 2) is the home page: an empty list and no live events.
  await page.route(/\/api\/jobs(\?.*)?$/, (r) =>
    r.fulfill(json({ items: [], next_cursor: null })),
  );
  await page.route("**/api/events**", (r) =>
    r.fulfill(json({ events: [], last_id: 0 })),
  );
  await page.route("**/api/runs?**", (r) => {
    const n = opts.reviewCount ?? 2;
    return r.fulfill(
      json({
        items: Array.from({ length: n }, (_, i) => ({
          id: `r${i}`,
          job_id: `j${i}`,
          company: "Acme",
          title: "SWE",
          status: "in_review",
          flagged: false,
          score: 80,
          coverage: "5/6",
          pages: 2,
          created_at: "2026-01-01T00:00:00Z",
          top_changes: [],
        })),
        next_cursor: null,
      }),
    );
  });
  // No separate draft: the profile page falls back to the approved profile.
  await page.route("**/api/profile/draft", (r) =>
    r.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ code: "not_found", message: "No draft" }),
    }),
  );
  // Profile page (Phase 1) also lists saved screening answers.
  await page.route("**/api/screening-answers", (r) => r.fulfill(json({ items: [] })));
  // Tracker (Phase 3): an empty board and no connected extension devices.
  await page.route("**/api/tracker", (r) =>
    r.fulfill(
      json({
        columns: {
          approved: [],
          applied: [],
          response: [],
          interview: [],
          offer: [],
          rejected: [],
        },
        stats: {
          applied_this_week: 0,
          response_rate: null,
          avg_match_score: null,
          counts: {
            approved: 0,
            applied: 0,
            response: 0,
            interview: 0,
            offer: 0,
            rejected: 0,
          },
        },
      }),
    ),
  );
  await page.route("**/api/extension/tokens", (r) => r.fulfill(json([])));
  await page.route("**/api/settings", async (r) => {
    const req = r.request();
    if (req.method() === "PUT") {
      state.puts.push({
        ifMatch: req.headers()["if-match"] ?? null,
        body: req.postDataJSON(),
      });
      state.rev += 1;
      state.theme = req.postDataJSON().theme;
    }
    return r.fulfill(
      json(
        {
          preferences: { ...prefs, theme: state.theme },
          configured: true,
          rev: state.rev,
          runs_used_today: 0,
          daily_cap: 5,
          cap_resets_at: "2026-01-02T00:00:00Z",
        },
        { etag: `"${state.rev}"` },
      ),
    );
  });
  return state;
}
