import { screen, waitFor, within } from "@testing-library/react";
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
  listJobs: vi.fn(),
  getJob: vi.fn(),
  patchJob: vi.fn(),
  addJob: vi.fn(),
  uploadImage: vi.fn(),
  tailorJob: vi.fn(),
  getEvents: vi.fn(),
}));
vi.mock("./api", () => api);
vi.mock("@/hooks/use-settings", async (orig) => ({
  ...(await orig<typeof import("@/hooks/use-settings")>()),
  useSettings: () => ({
    data: {
      runs_used_today: 2,
      daily_cap: 5,
      cap_resets_at: "2026-01-06T00:00:00Z",
    },
  }),
}));

import { Inbox } from "./inbox";
import { apiError, job, renderWithProviders } from "./test-utils";

const page = (items: ReturnType<typeof job>[], next: string | null = null) => ({
  items,
  next_cursor: next,
});

beforeEach(() => {
  vi.clearAllMocks();
  api.getEvents.mockResolvedValue({ events: [], last_id: 0 });
  api.getJob.mockResolvedValue({
    job: { status_reason: "The page needs a login" },
  });
});

describe("Inbox", () => {
  it("shows a skeleton, then rows with score numbers, CTC and red flags", async () => {
    api.listJobs.mockResolvedValue(
      page([
        job({ red_flags: ["Unpaid trial"] }),
        job({ id: "j2", title: "Backend", score: 55 }),
      ]),
    );
    renderWithProviders(<Inbox />);
    expect(screen.getByText("Loading your jobs…")).toBeInTheDocument();
    expect(
      await screen.findByRole("link", { name: "Frontend Engineer" }),
    ).toHaveAttribute("href", "/jobs/j1");
    expect(screen.getAllByText("30–40 LPA")).toHaveLength(2);
    expect(
      screen.getAllByRole("meter").map((m) => m.getAttribute("aria-valuenow")),
    ).toEqual(["82", "55"]);
    expect(screen.getByText("1 red flag")).toBeInTheDocument();
    expect(screen.getByText("2 of 5 runs today")).toBeInTheDocument();
  });

  it("renders processing, needs_paste and failed rows differently", async () => {
    api.listJobs.mockResolvedValue(
      page([
        job({
          id: "p",
          status: "processing",
          title: null,
          company: null,
          score: null,
        }),
        job({ id: "n", status: "needs_paste", score: null }),
        job({ id: "f", status: "failed", score: null }),
      ]),
    );
    renderWithProviders(<Inbox />);
    expect(await screen.findByText("Reading the posting…")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Submit text" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry with this text" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getAllByText(/The page needs a login/)).toHaveLength(2),
    );
    expect(screen.getAllByText(/there is no automatic retry/)).toHaveLength(1);
  });

  it("pastes text into a needs_paste row via PATCH {text} and keeps it on error", async () => {
    api.listJobs.mockResolvedValue(
      page([job({ status: "needs_paste", score: null })]),
    );
    api.patchJob.mockRejectedValueOnce(apiError(409, "invalid_state"));
    renderWithProviders(<Inbox />);
    const box = await screen.findByLabelText("Job description text");
    await userEvent.type(box, "We are hiring");
    await userEvent.click(screen.getByRole("button", { name: "Submit text" }));
    expect(await screen.findByText("invalid_state")).toBeInTheDocument();
    expect(box).toHaveValue("We are hiring");
    api.patchJob.mockResolvedValueOnce({});
    await userEvent.click(screen.getByRole("button", { name: "Submit text" }));
    await waitFor(() =>
      expect(api.patchJob).toHaveBeenLastCalledWith("j1", {
        text: "We are hiring",
      }),
    );
  });

  it("paginates with next_cursor", async () => {
    api.listJobs
      .mockResolvedValueOnce(page([job()], "c2"))
      .mockResolvedValueOnce(page([job({ id: "j2", title: "Second" })]));
    renderWithProviders(<Inbox />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Load more" }),
    );
    expect(
      await screen.findByRole("link", { name: "Second" }),
    ).toBeInTheDocument();
    expect(api.listJobs).toHaveBeenLastCalledWith({ sort: "created_at" }, "c2");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("filters by min score and sort", async () => {
    api.listJobs.mockResolvedValue(page([job()]));
    renderWithProviders(<Inbox />);
    await screen.findByRole("link", { name: "Frontend Engineer" });
    await userEvent.selectOptions(screen.getByLabelText("Minimum score"), "70");
    await waitFor(() =>
      expect(api.listJobs).toHaveBeenLastCalledWith(
        { sort: "created_at", min_score: 70 },
        undefined,
      ),
    );
    await userEvent.click(screen.getByRole("radio", { name: "Best match" }));
    await waitFor(() =>
      expect(api.listJobs).toHaveBeenLastCalledWith(
        { sort: "score", min_score: 70 },
        undefined,
      ),
    );
  });

  it("shows the empty state and an error with retry", async () => {
    api.listJobs.mockResolvedValueOnce(page([]));
    const { unmount } = renderWithProviders(<Inbox />);
    expect(
      await screen.findByText("Nothing in your inbox yet"),
    ).toBeInTheDocument();
    unmount();
    api.listJobs.mockRejectedValueOnce(apiError(500, "server_error"));
    api.listJobs.mockResolvedValueOnce(page([job()]));
    renderWithProviders(<Inbox />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't load your jobs",
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("link", { name: "Frontend Engineer" }),
    ).toBeInTheDocument();
  });

  it("Tailor selected: one call per job, per-job failures reported, failures stay selected", async () => {
    api.listJobs.mockResolvedValue(
      page([
        job({ id: "a", title: "A" }),
        job({ id: "b", title: "B" }),
        job({ id: "c", title: "C" }),
        job({ id: "d", title: "D" }),
      ]),
    );
    api.tailorJob.mockImplementation(async (id: string) => {
      if (id === "b") throw apiError(409, "no_profile");
      if (id === "c") throw apiError(429, "daily_cap", { used: 5, cap: 5 });
      return "run-" + id;
    });
    renderWithProviders(<Inbox />);
    await screen.findByRole("link", { name: "A" });
    await userEvent.click(
      screen.getByRole("checkbox", { name: /select all new jobs/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Tailor selected (4)" }),
    );
    const results = await screen.findByRole("region", {
      name: "Tailoring results",
    });
    expect(api.tailorJob.mock.calls).toEqual([
      ["a", false],
      ["b", false],
      ["c", false],
    ]);
    expect(
      within(results).getByText(/Approve your profile/),
    ).toBeInTheDocument();
    expect(
      within(results).getByText(/5 of 5 tailoring runs/),
    ).toBeInTheDocument();
    expect(
      within(results).getByText(/daily limit was reached/),
    ).toBeInTheDocument();
    // a succeeded; b, c, d stay selected
    expect(
      screen.getByRole("button", { name: "Tailor selected (3)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("checkbox", { name: /Select A at/ }),
    ).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Select B at/ })).toBeChecked();
  });

  it("red-flag jobs are not auto-confirmed in bulk", async () => {
    api.listJobs.mockResolvedValue(page([job({ red_flags: ["x"] })]));
    api.tailorJob.mockRejectedValue(
      apiError(409, "red_flags", { red_flags: ["x"] }),
    );
    renderWithProviders(<Inbox />);
    await userEvent.click(
      await screen.findByRole("checkbox", { name: /Select Frontend/ }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Tailor selected/ }),
    );
    expect(
      await screen.findByText(/Open the job to review them and confirm/),
    ).toBeInTheDocument();
    expect(api.tailorJob).toHaveBeenCalledWith("j1", false);
  });
});
