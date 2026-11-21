import type { Page } from "@playwright/test";
import { stubApi } from "./stubs";

type Job = Record<string, unknown>;
const mk = (over: Job): Job => ({
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
});

const jd = {
  title: "Frontend Engineer",
  company: "Acme",
  location: "Bengaluru",
  work_mode: "hybrid",
  experience_years_min: 3,
  experience_years_max: 6,
  ctc_lpa_min: 30,
  ctc_lpa_max: 40,
  seniority: "Senior",
  must_have: ["React"],
  nice_to_have: ["GraphQL"],
  responsibilities: ["Build the web app"],
  keywords: ["frontend"],
  red_flags: ["Unpaid trial period"],
  requested_resume_pages: null,
  source_url: null,
};

export type JobsStub = {
  added: unknown[];
  tailored: Array<{ id: string; body: unknown }>;
  patches: unknown[];
  runStatus: string;
};

export async function stubJobs(page: Page): Promise<JobsStub> {
  await stubApi(page, { reviewCount: 0 });
  const state: JobsStub = {
    added: [],
    tailored: [],
    patches: [],
    runStatus: "queued",
  };
  const json = (body: unknown, status = 200) => ({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
  const list = [
    mk({ id: "j1", red_flags: ["Unpaid trial period"] }),
    mk({ id: "j2", title: "Backend Engineer", score: 55 }),
    mk({
      id: "j3",
      status: "needs_paste",
      score: null,
      title: "Data Engineer",
    }),
    mk({
      id: "j4",
      status: "processing",
      score: null,
      title: null,
      company: null,
    }),
  ];
  const detail = (id: string) => {
    const s = list.find((j) => j.id === id)!;
    return {
      job: {
        id,
        source: "url",
        url: "https://acme.example/jobs/1",
        status: s.status,
        status_reason:
          s.status === "needs_paste" ? "The page needs a login" : null,
        company: s.company,
        title: s.title,
        score: s.score,
        red_flags: s.red_flags,
        max_pages_override:
          (state.patches.at(-1) as { max_pages_override?: number } | undefined)
            ?.max_pages_override ?? null,
        created_at: "2026-01-05T10:00:00Z",
        updated_at: "2026-01-05T10:00:00Z",
      },
      jd,
      score_breakdown: null,
      musts: [
        {
          skill: "React",
          status: "have",
          evidence_bullet_id: "abcdef0123456789",
        },
        { skill: "GraphQL", status: "ask", evidence_bullet_id: null },
        { skill: "Go", status: "missing", evidence_bullet_id: null },
      ],
      latest_run: state.tailored.length
        ? { id: "r1", status: state.runStatus }
        : null,
    };
  };
  const run = () => ({
    id: "r1",
    job_id: "j1",
    company: "Acme",
    title: "Frontend Engineer",
    status: state.runStatus,
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
    iterations: [{ iteration: 1, outcome: "Passed fact-check" }],
    has_pdf: false,
  });

  await page.route("**/api/events**", (r) =>
    r.fulfill(json({ events: [], last_id: 0 })),
  );
  await page.route("**/api/profile", (r) =>
    r.fulfill(
      json({
        id: "p",
        status: "approved",
        version: 1,
        resume_id: null,
        data: {
          experience: [
            {
              bullets: [
                { id: "abcdef0123456789", text: "Shipped the design system" },
              ],
            },
          ],
          projects: [],
        },
        created_at: "x",
        updated_at: "x",
        approved_at: "x",
      }),
    ),
  );
  await page.route(/\/api\/jobs(\?.*)?$/, async (r) => {
    const req = r.request();
    if (req.method() === "POST") {
      const body = req.postDataJSON();
      state.added.push(body);
      return r.fulfill(
        body.url?.includes("dup")
          ? json({ job_id: "j2", duplicate: true }, 200)
          : json({ job_id: "j9", status: "processing", duplicate: false }, 202),
      );
    }
    return r.fulfill(json({ items: list, next_cursor: null }));
  });
  await page.route(/\/api\/jobs\/[^/?]+\/tailor$/, async (r) => {
    const id = r.request().url().split("/").slice(-2)[0];
    state.tailored.push({ id, body: r.request().postDataJSON() });
    state.runStatus = "queued";
    return r.fulfill(json({ run_id: "r1" }, 202));
  });
  await page.route(/\/api\/jobs\/[^/?]+$/, async (r) => {
    const id = r.request().url().split("/").pop()!;
    if (r.request().method() === "PATCH") {
      state.patches.push(r.request().postDataJSON());
    }
    return r.fulfill(json(detail(id)));
  });
  await page.route(/\/api\/runs\/r1$/, (r) => r.fulfill(json(run())));
  await page.route(/\/api\/runs\/r1\/events$/, (r) => {
    // The stream ends in in_review; the client closes its own subscription there.
    state.runStatus = "in_review";
    const ev = (seq: number, type: string, payload: unknown) =>
      `id: ${seq}\nevent: ${type}\ndata: ${JSON.stringify({ seq, type, payload, ts: "x" })}\n\n`;
    return r.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body:
        ev(1, "status", { status: "running", from: "queued" }) +
        ev(2, "step", { step: "plan", iteration: 1 }) +
        ev(3, "status", { status: "in_review", from: "running" }),
    });
  });
  return state;
}
