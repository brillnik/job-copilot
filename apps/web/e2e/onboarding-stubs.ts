import type { Page, Route } from "@playwright/test";

type Json = Record<string, unknown>;

const ME = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "asha@example.com",
  name: "Asha Rao",
  auth_providers: ["google"],
  created_at: "2026-01-01T00:00:00Z",
  plan: "free",
};

const PREFS = {
  target_roles: [],
  cities: [],
  current_ctc_lpa: 0,
  expected_ctc_lpa: 0,
  notice_days: 30,
  default_length: "auto",
  template: "classic",
  daily_cap: 5,
  coverage_target: 0.7,
  theme: "system",
};

export const DRAFT_DATA = {
  contact: {
    name: "Asha Rao",
    email: "asha@example.com",
    phone: null,
    location: "Pune",
    links: ["https://asha.dev"],
  },
  summary: "Frontend engineer.",
  experience: [
    {
      id: "e1",
      company: "Acme",
      title: "Engineer",
      location: null,
      start: "2020",
      end: null,
      bullets: [{ id: "b1", text: "Cut p95 latency by 40% using React" }],
    },
  ],
  projects: [],
  education: [],
  skills: ["React", "Go"],
};

export type Onboarding = {
  consent: Json | null;
  draft: Json | null;
  approved: Json | null;
  configured: boolean;
  prefs: Json;
  rev: number;
  calls: string[];
  puts: Json[];
  settingsPuts: Array<{ ifMatch: string | null; body: Json }>;
  uploadMs: number;
};

const profile = (
  status: "draft" | "approved",
  data: unknown,
  version: number | null,
) => ({
  id: status === "draft" ? "p-draft" : "p-approved",
  status,
  version,
  resume_id: null,
  data,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  approved_at: status === "approved" ? "2026-01-02T00:00:00Z" : null,
});

/**
 * A small stateful fake of the profile/consent/settings endpoints, served to
 * the browser in place of the Next /api proxy. Mirrors the real API's
 * contracts: 404 for no approved profile / no draft, PUT /profile/draft creates
 * a draft, approve promotes it (the draft is gone afterwards).
 */
export async function stubOnboarding(
  page: Page,
  init: Partial<
    Pick<
      Onboarding,
      "consent" | "draft" | "approved" | "configured" | "uploadMs"
    >
  > = {},
): Promise<Onboarding> {
  const s: Onboarding = {
    consent: null,
    draft: null,
    approved: null,
    configured: false,
    prefs: { ...PREFS },
    rev: 1,
    calls: [],
    puts: [],
    settingsPuts: [],
    uploadMs: 800,
    ...init,
  };
  const ok = (
    route: Route,
    body: unknown,
    status = 200,
    headers: Record<string, string> = {},
  ) =>
    route.fulfill({
      status,
      contentType: "application/json",
      headers,
      body: JSON.stringify(body),
    });
  const notFound = (route: Route) =>
    ok(route, { code: "not_found", message: "Not found" }, 404);
  const log = (route: Route) =>
    s.calls.push(
      `${route.request().method()} ${new URL(route.request().url()).pathname}`,
    );

  // Lowest priority (registered first): other screens' reads get an empty page
  // instead of reaching the real proxy, which would answer 401 without a session.
  await page.route("**/api/**", (r) =>
    ok(r, { items: [], next_cursor: null, events: [], last_id: 0 }),
  );
  await page.route("**/api/me", (r) => ok(r, { ...ME, consent: s.consent }));
  await page.route("**/api/me/consent", (r) => {
    log(r);
    s.consent = {
      ...(r.request().postDataJSON() as Json),
      at: "2026-01-01T00:00:00Z",
    };
    return ok(r, s.consent, 201);
  });
  await page.route("**/api/runs?**", (r) =>
    ok(r, { items: [], next_cursor: null }),
  );
  await page.route("**/api/screening-answers", (r) => ok(r, { items: [] }));
  await page.route("**/api/profile", (r) =>
    s.approved ? ok(r, s.approved) : notFound(r),
  );
  await page.route("**/api/profile/draft", (r) => {
    const req = r.request();
    if (req.method() === "PUT") {
      log(r);
      const data = req.postDataJSON();
      s.puts.push(data);
      s.draft = profile("draft", data, null);
      return ok(r, s.draft);
    }
    return s.draft ? ok(r, s.draft) : notFound(r);
  });
  await page.route("**/api/profile/upload", async (r) => {
    log(r);
    const req = r.request();
    const body = req.postDataBuffer()?.toString("latin1") ?? "";
    if (
      !(req.headers()["content-type"] ?? "").startsWith(
        "multipart/form-data",
      ) ||
      !body.includes('name="file"')
    )
      return ok(
        r,
        { code: "validation_error", message: "bad", details: [] },
        422,
      );
    await new Promise((res) => setTimeout(res, s.uploadMs));
    s.draft = profile("draft", DRAFT_DATA, null);
    return ok(r, s.draft, 201);
  });
  await page.route("**/api/profile/approve", (r) => {
    log(r);
    if (!s.draft) return notFound(r);
    s.approved = profile("approved", (s.draft as { data: unknown }).data, 1);
    s.draft = null;
    return ok(r, s.approved);
  });
  await page.route("**/api/settings", (r) => {
    const req = r.request();
    if (req.method() === "PUT") {
      log(r);
      const body = req.postDataJSON() as Json;
      s.settingsPuts.push({ ifMatch: req.headers()["if-match"] ?? null, body });
      s.prefs = body;
      s.configured = true;
      s.rev += 1;
    }
    return ok(
      r,
      {
        preferences: s.prefs,
        configured: s.configured,
        rev: s.rev,
        runs_used_today: 0,
        daily_cap: 5,
        cap_resets_at: "2026-01-02T00:00:00Z",
      },
      200,
      { etag: `"${s.rev}"` },
    );
  });
  return s;
}

export const CONSENTED = {
  policy_version: "2026-01",
  at: "2026-01-01T00:00:00Z",
};
