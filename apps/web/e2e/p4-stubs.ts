import type { Page } from "@playwright/test";
import { stubApi } from "./stubs";

const json = (body: unknown, status = 200) => ({
  status,
  contentType: "application/json",
  body: JSON.stringify(body),
});

export const REC = {
  id: "rec1",
  catalog_job_id: "c1",
  score: 86,
  reasons: ["Skills match: React, TypeScript"],
  digest_date: "2026-11-19",
  action: "none",
  job_id: null as string | null,
  title: "Senior Frontend Engineer",
  company: "Acme",
  location: "Bengaluru",
  remote: true,
  apply_url: "https://example.com/apply",
  source_attribution: null,
};

const site = {
  acknowledged: false,
  acknowledged_at: null,
  policy_version: null,
  paused: false,
};

export type P4State = {
  saved: string[];
  dismissed: Array<{ id: string; reason: unknown }>;
  autopilotPuts: unknown[];
  training: unknown[];
};

/** Base shell stubs plus the Phase 4 endpoints (later routes win in Playwright). */
export async function stubP4(page: Page): Promise<P4State> {
  await stubApi(page);
  const st: P4State = {
    saved: [],
    dismissed: [],
    autopilotPuts: [],
    training: [],
  };
  let recs = [REC];
  let ap = {
    enabled: false,
    min_score: 75,
    daily_apply_cap: 15,
    digest_time: "19:00",
    sites_opt_in: { wellfound: site, naukri: site, hiring_cafe: site },
    policy_version: "2026-11",
    acknowledged_version: null as string | null,
    paused_sites: [],
  };
  let consent = { enabled: false } as Record<string, unknown>;

  await page.route("**/api/recommendations", (r) =>
    r.fulfill(json({ items: recs })),
  );
  await page.route("**/api/recommendations/*/save", (r) => {
    st.saved.push(r.request().url());
    recs = recs.map((x) => ({ ...x, action: "saved", job_id: "j1" }));
    return r.fulfill(json(recs[0]));
  });
  await page.route("**/api/recommendations/*/dismiss", (r) => {
    st.dismissed.push({
      id: "rec1",
      reason: r.request().postDataJSON().reason,
    });
    recs = [];
    return r.fulfill(json({ ...REC, action: "dismissed" }));
  });
  await page.route("**/api/autopilot", async (r) => {
    const req = r.request();
    if (req.method() === "PUT") {
      const b = req.postDataJSON();
      st.autopilotPuts.push(b);
      if (b.enabled)
        ap = {
          ...ap,
          enabled: true,
          acknowledged_version: b.acknowledgement_version,
        };
      if (b.enabled === false) ap = { ...ap, enabled: false };
      if (b.min_score !== undefined) ap = { ...ap, min_score: b.min_score };
    }
    return r.fulfill(json(ap));
  });
  await page.route("**/api/autopilot/digest**", (r) =>
    r.fulfill(
      json({
        date: "2026-11-19",
        submitted: [
          {
            application_id: "a1",
            job_id: "j1",
            company: "Acme",
            title: "SWE",
            status: "submitted",
          },
        ],
        needs_a_person: [],
        skipped: [
          {
            application_id: "a2",
            job_id: "j2",
            company: "Beta",
            title: "FE",
            status: "skipped",
            reason: "captcha",
            direct_link: "https://beta.example/apply",
          },
        ],
      }),
    ),
  );
  await page.route(/\/api\/applications(\?.*)?$/, (r) =>
    r.fulfill(
      json({
        items: [appl("a1", "submitted"), appl("a2", "skipped", "captcha")],
        next_cursor: null,
      }),
    ),
  );
  await page.route("**/api/applications/a2", (r) =>
    r.fulfill(json(appl("a2", "skipped", "captcha"))),
  );
  await page.route("**/api/screening-answers", (r) =>
    r.fulfill(
      json({
        items: [
          {
            id: "s1",
            question: "Notice period?",
            answer: "30 days",
            field_type: "text",
            source: "user",
            updated_at: "2026-11-01T00:00:00Z",
          },
        ],
      }),
    ),
  );
  await page.route("**/api/extension/pair-code", (r) =>
    r.fulfill(
      json({
        code: "ABCD-1234",
        expires_at: new Date(Date.now() + 600_000).toISOString(),
      }),
    ),
  );
  await page.route("**/api/integrations/gmail", (r) =>
    r.fulfill(
      json({
        enabled: true,
        connected: true,
        pending_suggestions: 1,
        connected_at: "2026-11-01T00:00:00Z",
      }),
    ),
  );
  await page.route("**/api/integrations/gmail/suggestions", (r) =>
    r.fulfill(
      json([
        {
          id: "g1",
          job_id: "j1",
          company: "Acme",
          title: "SWE",
          classification: "interview_invite",
          confidence: 0.9,
          suggested_column: "interview",
          status: "pending",
          received_at: "2026-11-19T00:00:00Z",
        },
      ]),
    ),
  );
  await page.route("**/api/me/training-consent", (r) => {
    const req = r.request();
    if (req.method() === "PUT") {
      const b = req.postDataJSON();
      st.training.push(b);
      consent = {
        enabled: b.enabled,
        policy_version: b.policy_version,
        at: "2026-11-19T00:00:00Z",
      };
    }
    return r.fulfill(json(consent));
  });
  return st;
}

function appl(id: string, status: string, skip: string | null = null) {
  return {
    id,
    job_id: `j-${id}`,
    run_id: `r-${id}`,
    company: id === "a1" ? "Acme" : "Beta",
    title: id === "a1" ? "SWE" : "FE",
    channel: "playwright",
    mode: "autopilot",
    ats: "greenhouse",
    site: "greenhouse",
    status,
    skip_reason: skip,
    direct_link: "https://beta.example/apply",
    submitted_at: null,
    answers_used: [
      {
        key: "email",
        label: "Email",
        required: true,
        source: "profile",
        value: "a@b.co",
      },
    ],
    screenshots: [],
    pending_fields: [],
    attempts: 1,
    created_at: "2026-11-19T09:00:00Z",
    updated_at: "2026-11-19T10:00:00Z",
  };
}
