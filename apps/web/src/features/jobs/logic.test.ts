import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  buildRunSteps,
  emptyProgress,
  humanizeStep,
  reduceStep,
} from "./run-steps";
import { fitChips } from "./fit";
import { dailyCapCopy, tailorProblem } from "./tailor-copy";
import { formatCtc } from "./format";
import { nextDelay } from "./use-job-events";
import { apiError } from "./test-utils";
import type { JobDescription } from "./types";
import { validateImage } from "./add-job-modal";

describe("buildRunSteps", () => {
  it("queued: only the queue step runs", () => {
    const s = buildRunSteps("queued", emptyProgress);
    expect(s[0]).toMatchObject({ state: "running" });
    expect(s.slice(1).every((x) => x.state === "queued")).toBe(true);
  });

  it("marks earlier steps done and the current one running", () => {
    let p = emptyProgress;
    p = reduceStep(p, "load_context", 1);
    p = reduceStep(p, "rank_items", 1);
    p = reduceStep(p, "plan", 1);
    const s = buildRunSteps("running", p);
    expect(s.map((x) => x.state)).toEqual([
      "done",
      "done",
      "done",
      "running",
      "queued",
      "queued",
      "queued",
    ]);
  });

  it("waiting_for_user shows the current step as waiting", () => {
    const p = reduceStep(emptyProgress, "plan", 1);
    const s = buildRunSteps("waiting_for_user", p);
    expect(s.find((x) => x.state === "waiting")?.label).toBe("Plan the resume");
  });

  it("unknown steps are shown generically, in arrival order", () => {
    let p = reduceStep(emptyProgress, "load_context");
    p = reduceStep(p, "polish_tone");
    const s = buildRunSteps("running", p);
    expect(s[2]).toMatchObject({ label: "Polish tone", state: "running" });
    expect(humanizeStep("")).toBe("Working");
  });

  it("a repeated step (new iteration) goes back to running with its iteration", () => {
    let p = emptyProgress;
    for (const n of ["write_draft", "fact_check", "write_draft"])
      p = reduceStep(p, n, n === "fact_check" ? 1 : p.order.length ? 2 : 1);
    const s = buildRunSteps("running", p);
    const draft = s.find((x) => x.label === "Write the draft")!;
    expect(draft.state).toBe("running");
    expect(draft.detail).toBe("Iteration 2");
    expect(s.find((x) => x.label === "Fact-check every claim")!.state).toBe(
      "queued",
    );
  });

  it("falls back to current_step after a reload and finishes cleanly", () => {
    expect(
      buildRunSteps("running", emptyProgress, "fact_check").some(
        (x) => x.label === "Fact-check every claim" && x.state === "running",
      ),
    ).toBe(true);
    const done = buildRunSteps("in_review", reduceStep(emptyProgress, "plan"));
    expect(done.every((x) => x.state === "done")).toBe(true);
  });

  it("stopped runs mark the last step as stopped", () => {
    const s = buildRunSteps(
      "needs_attention",
      reduceStep(emptyProgress, "plan"),
    );
    expect(s.at(-1)).toMatchObject({ detail: "Stopped", state: "queued" });
  });
});

describe("fitChips", () => {
  const prefs = {
    expected_ctc_lpa: 28,
    notice_days: 30,
    cities: ["Bengaluru"],
  };
  const jd = {
    work_mode: "onsite",
    location: "Bengaluru, KA",
    ctc_lpa_min: 30,
    ctc_lpa_max: 40,
  } as unknown as JobDescription;

  it("compares CTC to the expectation and location to the user's cities", () => {
    const chips = fitChips(jd, prefs);
    expect(chips.find((c) => c.key === "ctc")).toMatchObject({ tone: "ok" });
    expect(chips.find((c) => c.key === "loc")).toMatchObject({ tone: "ok" });
    const low = fitChips({ ...jd, ctc_lpa_max: 20, location: "Pune" }, prefs);
    expect(low.find((c) => c.key === "ctc")?.tone).toBe("warn");
    expect(low.find((c) => c.key === "loc")?.tone).toBe("warn");
  });

  it("does not invent a notice verdict", () => {
    const n = fitChips(jd, prefs).find((c) => c.key === "notice")!;
    expect(n.tone).toBe("neutral");
    expect(n.text).toContain("doesn't state one");
  });

  it("handles a posting without CTC and no prefs", () => {
    expect(fitChips({ work_mode: "unknown" } as never)[0].text).toMatch(
      /not stated/,
    );
    expect(fitChips(null, prefs)).toEqual([]);
  });
});

describe("tailorProblem", () => {
  it.each([
    ["jd_not_ready", 409, /isn't ready yet/],
    ["no_profile", 409, /Approve your profile/],
    ["profile_indexing", 409, /still being indexed/],
    ["run_in_progress", 409, /already in progress/],
    ["invalid_state", 409, /current state/],
  ])("%s", (code, status, re) => {
    expect(tailorProblem(apiError(status, code)).message).toMatch(re);
  });

  it("red_flags carries the flags; run_in_progress the run id; no_profile a fix link", () => {
    expect(
      tailorProblem(apiError(409, "red_flags", { red_flags: ["a"] })).redFlags,
    ).toEqual(["a"]);
    expect(
      tailorProblem(apiError(409, "run_in_progress", { run_id: "r9" })).runId,
    ).toBe("r9");
    expect(tailorProblem(apiError(409, "no_profile")).fix?.href).toBe(
      "/profile",
    );
  });

  it("daily_cap uses used and cap", () => {
    expect(
      tailorProblem(apiError(429, "daily_cap", { used: 5, cap: 5 })).message,
    ).toContain("5 of 5");
    expect(dailyCapCopy(2, 3)).toBe("You've used 2 of 3 tailoring runs today.");
  });

  it("falls back for unknown errors", () => {
    expect(tailorProblem(new Error("x")).code).toBe("unknown");
    expect(tailorProblem(apiError(500, "server_error")).message).toBe(
      "server_error",
    );
  });
});

describe("misc", () => {
  it("formatCtc", () => {
    expect(formatCtc(30, 40)).toBe("30–40 LPA");
    expect(formatCtc(null, 12.5)).toBe("up to 12.5 LPA");
    expect(formatCtc(null, null)).toBeNull();
  });
  it("poll delay backs off and resets", () => {
    expect(nextDelay(3000, false)).toBe(4500);
    expect(nextDelay(14000, false)).toBe(15000);
    expect(nextDelay(15000, true)).toBe(3000);
  });
  it("validateImage", () => {
    const f = (type: string, size: number) =>
      new File([new Uint8Array(size)], "a", { type });
    expect(validateImage(f("image/png", 10))).toBeNull();
    expect(validateImage(f("image/gif", 10))).toMatch(/PNG and JPEG/);
    expect(validateImage(f("image/jpeg", 5 * 1024 * 1024 + 1))).toMatch(/5 MB/);
  });
});

beforeEach(() => vi.clearAllMocks());
