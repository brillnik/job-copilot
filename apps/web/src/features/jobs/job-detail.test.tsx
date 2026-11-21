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
  getJob: vi.fn(),
  patchJob: vi.fn(),
  getEvents: vi.fn(),
  getRun: vi.fn(),
  tailorJob: vi.fn(),
  answerRun: vi.fn(),
  cancelRun: vi.fn(),
}));
vi.mock("./api", () => api);
const browser = vi.hoisted(() => ({ GET: vi.fn() }));
vi.mock("@/lib/api/browser", () => ({ api: browser }));
vi.mock("@/hooks/use-event-stream", () => ({ useEventStream: () => "open" }));
vi.mock("@/hooks/use-settings", async (orig) => ({
  ...(await orig<typeof import("@/hooks/use-settings")>()),
  useSettings: () => ({
    data: {
      runs_used_today: 1,
      daily_cap: 5,
      cap_resets_at: "2026-01-06T00:00:00Z",
      preferences: {
        expected_ctc_lpa: 28,
        notice_days: 30,
        cities: ["Bengaluru"],
      },
    },
  }),
}));

import { JobDetailScreen } from "./job-detail";
import { apiError, detail, renderWithProviders } from "./test-utils";

beforeEach(() => {
  vi.clearAllMocks();
  api.getEvents.mockResolvedValue({ events: [], last_id: 0 });
  browser.GET.mockResolvedValue({
    data: {
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
    },
    response: new Response(),
  });
});

describe("JobDetailScreen", () => {
  it("renders the structured JD, score and fit chips", async () => {
    api.getJob.mockResolvedValue(detail());
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Frontend Engineer",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Match score" })).toHaveAttribute(
      "aria-valuenow",
      "82",
    );
    expect(
      screen.getByText(/meets your 28 LPA expectation/),
    ).toBeInTheDocument();
    expect(screen.getByText(/is one of your cities/)).toBeInTheDocument();
    expect(screen.getByText(/Your notice period: 30 days/)).toBeInTheDocument();
    expect(screen.getByText("Build the web app")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Original posting/ }),
    ).toHaveAttribute("href", "https://acme.example/jobs/1");
  });

  it("must-have chips: have (with evidence text), ask, missing, unknown", async () => {
    api.getJob.mockResolvedValue(detail());
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    const list = await screen.findByRole("list", { name: "Must-have skills" });
    expect(within(list).getByText(/Have:/)).toBeInTheDocument();
    expect(within(list).getByText(/Ask:/)).toBeInTheDocument();
    expect(within(list).getByText(/Missing:/)).toBeInTheDocument();
    expect(within(list).getByText(/Not assessed:/)).toBeInTheDocument();
    // The evidence chip resolves the bullet text from the approved profile.
    const chip = await within(list).findByRole("button", { name: "abcdef01" });
    expect(chip).toHaveAccessibleDescription(/Shipped the design system/);
  });

  it("shows only the id when the profile lacks that bullet", async () => {
    api.getJob.mockResolvedValue(detail());
    browser.GET.mockRejectedValue(new Error("404"));
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    const list = await screen.findByRole("list", { name: "Must-have skills" });
    await waitFor(() =>
      expect(within(list).getByText("abcdef01")).toBeInTheDocument(),
    );
    expect(within(list).queryByRole("button")).toBeNull();
  });

  it("lists red flags", async () => {
    const d = detail();
    d.job.red_flags = ["Unpaid trial period"];
    api.getJob.mockResolvedValue(d);
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    const h = await screen.findByRole("heading", { name: "Red flags" });
    expect(h.closest("section")).toHaveTextContent("Unpaid trial period");
  });

  it("page length: Auto sends null, a number sends that number", async () => {
    api.getJob.mockResolvedValue(detail());
    const two = detail();
    two.job.max_pages_override = 2;
    api.patchJob.mockResolvedValue(two);
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("radio", { name: "Auto" })).toBeChecked();
    api.getJob.mockResolvedValue(two); // the refetch after saving sees the new value
    await userEvent.click(screen.getByRole("radio", { name: "2 pages" }));
    await waitFor(() =>
      expect(api.patchJob).toHaveBeenCalledWith("j1", {
        max_pages_override: 2,
      }),
    );
    expect(await screen.findByText("Saved.")).toBeInTheDocument();
    api.patchJob.mockResolvedValue(detail());
    await userEvent.click(screen.getByRole("radio", { name: "Auto" }));
    await waitFor(() =>
      expect(api.patchJob).toHaveBeenLastCalledWith("j1", {
        max_pages_override: null,
      }),
    );
  });

  it("reports a failed save without losing the control", async () => {
    api.getJob.mockResolvedValue(detail());
    api.patchJob.mockRejectedValue(apiError(422, "invalid"));
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    await screen.findByRole("heading", { level: 1 });
    await userEvent.click(screen.getByRole("radio", { name: "3 pages" }));
    expect(
      await screen.findByText(/Couldn't save: invalid/),
    ).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Auto" })).toBeChecked();
  });

  it("needs_paste shows the paste box and PATCHes text", async () => {
    const d = detail({ jd: null, musts: [] });
    d.job.status = "needs_paste";
    d.job.status_reason = "Page requires login";
    d.job.score = null;
    api.getJob.mockResolvedValue(d);
    api.patchJob.mockResolvedValue({
      ...d,
      job: { ...d.job, status: "processing" },
    });
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    expect(await screen.findByText(/Page requires login/)).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText("Job description text"),
      "JD body",
    );
    await userEvent.click(screen.getByRole("button", { name: "Submit text" }));
    await waitFor(() =>
      expect(api.patchJob).toHaveBeenCalledWith("j1", { text: "JD body" }),
    );
  });

  it("processing shows a skeleton", async () => {
    const d = detail({ jd: null, musts: [] });
    d.job.status = "processing";
    d.job.score = null;
    api.getJob.mockResolvedValue(d);
    renderWithProviders(<JobDetailScreen jobId="j1" />);
    expect(await screen.findAllByText(/Reading the posting/)).not.toHaveLength(
      0,
    );
  });

  it("404 and load errors", async () => {
    api.getJob.mockRejectedValueOnce(apiError(404, "not_found"));
    const { unmount } = renderWithProviders(<JobDetailScreen jobId="x" />);
    expect(await screen.findByText("Job not found")).toBeInTheDocument();
    unmount();
    api.getJob.mockRejectedValueOnce(apiError(500, "server_error"));
    api.getJob.mockResolvedValueOnce(detail());
    renderWithProviders(<JobDetailScreen jobId="x" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Try again" }),
    );
    expect(
      await screen.findByRole("heading", { level: 1 }),
    ).toBeInTheDocument();
  });
});
