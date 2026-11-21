import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
const api = vi.hoisted(() => ({
  tailorJob: vi.fn(),
  getRun: vi.fn(),
  answerRun: vi.fn(),
  cancelRun: vi.fn(),
}));
vi.mock("./api", () => api);
const stream = vi.hoisted(() => ({
  opts: null as null | {
    url: string | null;
    onMessage: (m: { data: unknown }) => void;
    isTerminal?: (m: { data: unknown }) => boolean;
  },
}));
vi.mock("@/hooks/use-event-stream", () => ({
  useEventStream: (o: typeof stream.opts) => {
    stream.opts = o;
    return "open";
  },
}));
const settings = vi.hoisted(() => ({ used: 2 }));
vi.mock("@/hooks/use-settings", async (orig) => ({
  ...(await orig<typeof import("@/hooks/use-settings")>()),
  useSettings: () => ({
    data: {
      runs_used_today: settings.used,
      daily_cap: 5,
      cap_resets_at: "2026-01-06T00:00:00Z",
    },
  }),
}));

import { act } from "@testing-library/react";
import { TailorPanel } from "./tailor-panel";
import { apiError, detail, renderWithProviders, run } from "./test-utils";

beforeEach(() => {
  vi.clearAllMocks();
  settings.used = 2;
  stream.opts = null;
});

const withRedFlags = () => {
  const d = detail();
  d.job.red_flags = ["Unpaid trial period"];
  return d;
};

describe("TailorPanel start", () => {
  it("shows runs used of cap and starts a run", async () => {
    api.tailorJob.mockResolvedValue("r1");
    api.getRun.mockResolvedValue(run({ status: "queued", current_step: null }));
    renderWithProviders(<TailorPanel detail={detail()} />);
    expect(screen.getByText("2 of 5 runs today")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor resume" }),
    );
    expect(api.tailorJob).toHaveBeenCalledWith("j1", false);
    expect(
      await screen.findByRole("list", { name: "Tailoring progress" }),
    ).toBeInTheDocument();
    expect(stream.opts?.url).toBe("/api/runs/r1/events");
  });

  it("asks to confirm red flags in a dialog before calling the API", async () => {
    api.tailorJob.mockResolvedValue("r1");
    api.getRun.mockResolvedValue(run({ status: "queued" }));
    renderWithProviders(<TailorPanel detail={withRedFlags()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor resume" }),
    );
    expect(api.tailorJob).not.toHaveBeenCalled();
    expect(await screen.findByText("Unpaid trial period")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor anyway" }),
    );
    await waitFor(() => expect(api.tailorJob).toHaveBeenCalledWith("j1", true));
  });

  it("opens the dialog from a server red_flags 409 too", async () => {
    api.tailorJob.mockRejectedValue(
      apiError(409, "red_flags", { red_flags: ["Pay to apply"] }),
    );
    renderWithProviders(<TailorPanel detail={detail()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor resume" }),
    );
    expect(await screen.findByText("Pay to apply")).toBeInTheDocument();
  });

  it.each([
    ["jd_not_ready", 409, undefined, /isn't ready yet/],
    ["no_profile", 409, undefined, /Approve your profile/],
    ["profile_indexing", 409, undefined, /still being indexed/],
    ["invalid_state", 409, undefined, /current state/],
    ["daily_cap", 429, { used: 5, cap: 5 }, /used 5 of 5 tailoring runs today/],
  ])("shows the copy for %s", async (code, status, details, re) => {
    api.tailorJob.mockRejectedValue(apiError(status, code, details));
    renderWithProviders(<TailorPanel detail={detail()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor resume" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(re);
  });

  it("no_profile links to the profile; run_in_progress resumes that run", async () => {
    api.tailorJob.mockRejectedValueOnce(apiError(409, "no_profile"));
    renderWithProviders(<TailorPanel detail={detail()} />);
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor resume" }),
    );
    expect(
      await screen.findByRole("link", { name: "Go to your profile" }),
    ).toHaveAttribute("href", "/profile");
    api.tailorJob.mockRejectedValueOnce(
      apiError(409, "run_in_progress", { run_id: "r9" }),
    );
    api.getRun.mockResolvedValue(run({ id: "r9", status: "running" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor resume" }),
    );
    await waitFor(() => expect(api.getRun).toHaveBeenCalledWith("r9"));
    expect(await screen.findByText(/already in progress/)).toBeInTheDocument();
  });

  it("disables Start at the daily cap and says why", () => {
    settings.used = 5;
    renderWithProviders(<TailorPanel detail={detail()} />);
    expect(
      screen.getByRole("button", { name: "Tailor resume" }),
    ).toBeDisabled();
    expect(screen.getByText(/used 5 of 5 tailoring runs/)).toBeInTheDocument();
  });

  it("explains when the job cannot be tailored yet", () => {
    const d = detail();
    d.job.status = "needs_paste";
    renderWithProviders(<TailorPanel detail={d} />);
    expect(screen.queryByRole("button", { name: /Tailor resume/ })).toBeNull();
    expect(
      screen.getByText(/once the posting has been read/),
    ).toBeInTheDocument();
  });
});

describe("TailorPanel run states", () => {
  it("resumes an in-progress run on load and cancels it", async () => {
    api.getRun.mockResolvedValue(
      run({ id: "r5", status: "running", current_step: "write_draft" }),
    );
    api.cancelRun.mockResolvedValue({ run_id: "r5", status: "cancelled" });
    renderWithProviders(
      <TailorPanel
        detail={detail({ latest_run: { id: "r5", status: "running" } })}
      />,
    );
    expect(
      await screen.findByRole("list", { name: "Tailoring progress" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Write the draft")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel run" }));
    await waitFor(() => expect(api.cancelRun).toHaveBeenCalledWith("r5"));
  });

  it("updates the stepper from SSE step events", async () => {
    api.getRun.mockResolvedValue(
      run({ status: "running", current_step: null }),
    );
    renderWithProviders(
      <TailorPanel
        detail={detail({ latest_run: { id: "r1", status: "running" } })}
      />,
    );
    await screen.findByRole("list", { name: "Tailoring progress" });
    act(() =>
      stream.opts!.onMessage({
        data: {
          seq: 1,
          type: "step",
          payload: { step: "rank_items", iteration: 1 },
          ts: "x",
        },
      }),
    );
    const current = screen
      .getByText("Pick your most relevant experience")
      .closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
    // The client closes its own subscription at in_review (not terminal server-side).
    expect(
      stream.opts!.isTerminal!({
        data: { type: "status", payload: { status: "in_review" } },
      }),
    ).toBe(true);
    expect(
      stream.opts!.isTerminal!({ data: { type: "step", payload: {} } }),
    ).toBe(false);
  });

  it("asks the agent's questions and posts the answers", async () => {
    api.getRun.mockResolvedValue(
      run({
        status: "waiting_for_user",
        pending_questions: [
          { skill: "GraphQL", prompt: "Have you used GraphQL in production?" },
          { skill: "Go", prompt: null },
        ],
      }),
    );
    api.answerRun.mockResolvedValue({ run_id: "r1", status: "queued" });
    renderWithProviders(
      <TailorPanel
        detail={detail({
          latest_run: { id: "r1", status: "waiting_for_user" },
        })}
      />,
    );
    expect(
      await screen.findByText("Have you used GraphQL in production?"),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));
    expect(
      await screen.findByText("Answer every question to continue."),
    ).toBeInTheDocument();
    expect(api.answerRun).not.toHaveBeenCalled();
    await userEvent.click(screen.getAllByRole("radio", { name: "Yes" })[0]);
    await userEvent.type(
      screen.getByLabelText(/Details about GraphQL/),
      "Apollo at Acme",
    );
    await userEvent.click(screen.getAllByRole("radio", { name: "No" })[1]);
    await userEvent.click(screen.getByRole("button", { name: "Send answers" }));
    await waitFor(() =>
      expect(api.answerRun).toHaveBeenCalledWith("r1", [
        { skill: "GraphQL", answer: "yes", detail: "Apollo at Acme" },
        { skill: "Go", answer: "no" },
      ]),
    );
  });

  it("links to the review screen when in_review, with iteration history", async () => {
    api.getRun.mockResolvedValue(
      run({
        status: "in_review",
        iterations: [
          { iteration: 1, outcome: "Coverage below target" },
          { iteration: 2, outcome: "Passed" },
        ],
      }),
    );
    renderWithProviders(
      <TailorPanel
        detail={detail({ latest_run: { id: "r1", status: "in_review" } })}
      />,
    );
    expect(
      await screen.findByRole("link", { name: "Open review" }),
    ).toHaveAttribute("href", "/review/r1");
    expect(screen.getByText("Coverage below target")).toBeInTheDocument();
    expect(stream.opts).toBeNull(); // no stream for a finished run
  });

  it("needs_attention offers a retry via a new tailor call", async () => {
    api.getRun.mockResolvedValue(
      run({ status: "needs_attention", status_reason: "llm_unreachable" }),
    );
    api.tailorJob.mockResolvedValue("r2");
    renderWithProviders(
      <TailorPanel
        detail={detail({ latest_run: { id: "r1", status: "needs_attention" } })}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /needs attention/,
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() =>
      expect(api.tailorJob).toHaveBeenCalledWith("j1", false),
    );
  });

  it("shows an error with retry when the run can't be loaded", async () => {
    api.getRun.mockRejectedValueOnce(apiError(500, "server_error"));
    renderWithProviders(
      <TailorPanel
        detail={detail({ latest_run: { id: "r1", status: "running" } })}
      />,
    );
    expect(
      await screen.findByText("Couldn't load the run"),
    ).toBeInTheDocument();
    api.getRun.mockResolvedValueOnce(run({ status: "running" }));
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("list", { name: "Tailoring progress" }),
    ).toBeInTheDocument();
  });
});
