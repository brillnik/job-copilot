import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

const GET = vi.fn();
const POST = vi.fn();
const PUT = vi.fn();
vi.mock("@/lib/api/browser", () => ({
  api: {
    GET: (...a: unknown[]) => GET(...a),
    POST: (...a: unknown[]) => POST(...a),
    PUT: (...a: unknown[]) => PUT(...a),
  },
}));
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...p
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...p}>
      {children}
    </a>
  ),
}));

import { ToastProvider } from "@/components/ui/toast";
import { splitDiff } from "./bullet-card";
import { reviewErrorMessage } from "./api";
import { runFixture, summaryFixture } from "./fixtures";
import { ReviewDetail } from "./review-detail";
import { ReviewQueue } from "./review-queue";
import { ApiError } from "@/lib/api/errors";

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}
const ok = (data: unknown) => ({ data, response: new Response() });
const fail = (status: number, code: string, details?: unknown) => ({
  error: { code, message: `msg ${code}`, details },
  response: new Response(null, { status }),
});

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  PUT.mockReset();
  push.mockReset();
});

describe("splitDiff", () => {
  it("splits the server diff into master and tailored sides without recomputing", () => {
    const { master, tailored } = splitDiff({
      source_text: "a b",
      tailored_text: "a c",
      diff: [
        { op: "same", text: "a " },
        { op: "del", text: "b" },
        { op: "add", text: "c" },
      ],
    });
    expect(master).toEqual([
      { text: "a ", kind: "same" },
      { text: "b", kind: "del" },
    ]);
    expect(tailored).toEqual([
      { text: "a ", kind: "same" },
      { text: "c", kind: "ins" },
    ]);
  });
});

describe("reviewErrorMessage", () => {
  it("explains the daily cap with the numbers and pdf_not_ready in plain words", () => {
    expect(
      reviewErrorMessage(
        new ApiError({
          code: "daily_cap",
          message: "x",
          status: 429,
          details: { used: 5, cap: 5 },
        }),
      ),
    ).toMatch(/5 of 5/);
    expect(
      reviewErrorMessage(
        new ApiError({ code: "pdf_not_ready", message: "x", status: 409 }),
      ),
    ).toMatch(/still being rendered/);
  });
});

describe("ReviewDetail", () => {
  it("shows both diff sides, the revert reason, coverage and page fit, with no axe violations", async () => {
    GET.mockResolvedValue(ok(runFixture({ flagged: true })));
    const { container } = wrap(<ReviewDetail runId="run1" />);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: /Frontend Engineer at Acme/,
      }),
    ).toBeVisible();
    expect(screen.getAllByText("Master:").length).toBe(2);
    expect(screen.getAllByText("Tailored:").length).toBe(2);
    expect(screen.getByText(/The rewrite introduced a number/)).toBeVisible();
    expect(screen.getByText("67%")).toBeVisible();
    expect(screen.getByText(/Fits: 2 pages of 2/)).toBeVisible();
    expect(screen.getAllByText(/Flagged/).length).toBeGreaterThan(0);
    expect(screen.getByTitle("Resume PDF preview")).toHaveAttribute(
      "src",
      "/api/runs/run1/pdf?draft=latest&v=3",
    );
    expect(
      await axe(container, { iframes: false } as never),
    ).toHaveNoViolations();
  });

  it("disables Approve until the PDF is ready", async () => {
    GET.mockResolvedValue(ok(runFixture({ has_pdf: false })));
    wrap(<ReviewDetail runId="run1" />);
    expect(
      await screen.findByRole("button", { name: "Approve" }),
    ).toBeDisabled();
    expect(screen.getAllByText(/Rendering the PDF/).length).toBeGreaterThan(0);
  });

  it("saves edits with If-Match, and keeps refused text with the violation shown", async () => {
    GET.mockResolvedValue(ok(runFixture()));
    PUT.mockResolvedValue(
      ok({
        run: runFixture({
          has_pdf: false,
          draft_rev: 4,
          summary: "Frontend engineer with 6 years building design systems.",
        }),
        applied: ["cover_note"],
        violations: [
          {
            code: "invented_number",
            field: "summary",
            source_id: null,
            term: "10",
            message: "10 is not in your profile",
            blocked: true,
          },
        ],
      }),
    );
    wrap(<ReviewDetail runId="run1" />);
    const user = userEvent.setup();
    const summary = await screen.findByLabelText("Edit summary");
    await user.clear(summary);
    await user.type(summary, "Engineer with 10 years");
    await user.type(screen.getByLabelText("Edit cover note"), " Thanks!");
    await user.click(screen.getByRole("button", { name: /Save 2 edits/ }));
    await waitFor(() => expect(PUT).toHaveBeenCalled());
    const call = PUT.mock.calls[0];
    expect(call[0]).toBe("/runs/{run_id}/draft");
    expect(call[1].params.header).toEqual({ "if-match": '"3"' });
    expect(call[1].body).toEqual({
      summary: "Engineer with 10 years",
      cover_note: "Hello Acme team. Thanks!",
    });
    expect(
      (await screen.findAllByText(/10 is not in your profile/)).length,
    ).toBeGreaterThan(0);
    expect(screen.getByLabelText("Edit summary")).toHaveValue(
      "Engineer with 10 years",
    );
    expect(screen.getByRole("button", { name: /Save 1 edit$/ })).toBeVisible();
  });

  it("offers to reload on a stale write and keeps the text", async () => {
    GET.mockResolvedValue(ok(runFixture()));
    PUT.mockResolvedValue(fail(409, "stale_write", { rev: 5 }));
    wrap(<ReviewDetail runId="run1" />);
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Edit cover note"), " more");
    await user.click(screen.getByRole("button", { name: /Save 1 edit/ }));
    expect(
      await screen.findByRole("button", { name: "Load latest draft" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Edit cover note")).toHaveValue(
      "Hello Acme team. more",
    );
  });

  it("approves and reports pdf_not_ready honestly", async () => {
    GET.mockResolvedValue(ok(runFixture()));
    POST.mockResolvedValue(fail(409, "pdf_not_ready"));
    wrap(<ReviewDetail runId="run1" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Approve" }),
    );
    expect(
      (await screen.findAllByText(/still being rendered/)).length,
    ).toBeGreaterThan(0);
  });

  it("asks to confirm red flags when regenerating, then retries with confirm_red_flags", async () => {
    GET.mockResolvedValue(ok(runFixture()));
    POST.mockResolvedValueOnce(
      fail(409, "red_flags", { red_flags: ["Unpaid trial"] }),
    ).mockResolvedValueOnce(ok({ run_id: "run2" }));
    wrap(<ReviewDetail runId="run1" />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("radio", { name: "3 pages" }));
    await user.click(
      screen.getByRole("button", { name: "Regenerate at 3 pages" }),
    );
    expect(await screen.findByText("Unpaid trial")).toBeVisible();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Regenerate anyway" }));
    await waitFor(() => expect(POST).toHaveBeenCalledTimes(2));
    expect(POST.mock.calls[1][1].body).toMatchObject({
      max_pages: 3,
      confirm_red_flags: true,
    });
    await waitFor(() => expect(push).toHaveBeenCalledWith("/jobs/job1"));
  });

  it("links back to the job when the run is not reviewable yet", async () => {
    GET.mockResolvedValue(
      ok(
        runFixture({
          status: "running",
          bullets: [],
          summary: null,
          coverage: null,
          pages: null,
          has_pdf: false,
        }),
      ),
    );
    wrap(<ReviewDetail runId="run1" />);
    expect(
      await screen.findByRole("link", { name: "Go to the job" }),
    ).toHaveAttribute("href", "/jobs/job1");
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("is read-only once approved and points to the approved PDF", async () => {
    GET.mockResolvedValue(ok(runFixture({ status: "approved" })));
    wrap(<ReviewDetail runId="run1" />);
    expect(await screen.findByText("Approved PDF")).toBeVisible();
    expect(screen.queryByLabelText("Edit summary")).toBeNull();
    expect(screen.getByRole("link", { name: /Open PDF/ })).toHaveAttribute(
      "href",
      "/api/runs/run1/pdf?draft=approved",
    );
  });

  it("shows a retryable error state", async () => {
    GET.mockResolvedValue(fail(500, "server_error"));
    wrap(<ReviewDetail runId="run1" />);
    expect(
      await screen.findByRole(
        "button",
        { name: "Try again" },
        { timeout: 4000 },
      ),
    ).toBeVisible();
  });
});

describe("ReviewQueue", () => {
  it("lists drafts and opens the detail when approve hits pdf_not_ready", async () => {
    GET.mockResolvedValue(ok({ items: [summaryFixture()], next_cursor: null }));
    POST.mockResolvedValue(fail(409, "pdf_not_ready"));
    wrap(<ReviewQueue />);
    expect(await screen.findByText("Added React keywords")).toBeVisible();
    expect(screen.getByText("Coverage 5/6")).toBeVisible();
    await userEvent.click(
      screen.getByRole("button", { name: "Approve Frontend Engineer at Acme" }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith("/review/run1"));
  });

  it("shows the empty state", async () => {
    GET.mockResolvedValue(ok({ items: [], next_cursor: null }));
    wrap(<ReviewQueue />);
    expect(await screen.findByText("Nothing to review")).toBeVisible();
  });
});
