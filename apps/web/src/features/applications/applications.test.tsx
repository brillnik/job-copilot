import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/features/common/test-utils";
import { callsTo, err, resetApi, routes } from "@/features/common/fake-api";
import { ApplicationDetail } from "./application-detail";
import { ApplicationList } from "./application-list";
import { ApplyRun } from "./apply-run";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/browser", async () => ({
  api: (await import("@/features/common/fake-api")).fakeClient,
}));
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

const app = (over = {}) => ({
  id: "a1",
  job_id: "j1",
  run_id: "r1",
  company: "Acme",
  title: "SWE",
  channel: "playwright",
  mode: "manual",
  ats: "greenhouse",
  site: "greenhouse",
  status: "submitted",
  skip_reason: null,
  direct_link: "https://acme.example/apply",
  submitted_at: "2026-11-19T10:00:00Z",
  answers_used: [],
  screenshots: [],
  pending_fields: [],
  attempts: 1,
  created_at: "2026-11-19T09:00:00Z",
  updated_at: "2026-11-19T10:00:00Z",
  ...over,
});

beforeEach(() => {
  resetApi();
  push.mockClear();
});

describe("ApplicationList", () => {
  it("shows status as text, the skip reason, and loads more by cursor", async () => {
    routes["GET /applications"] = ({ params }) => {
      const cursor = (params as { query: { cursor?: string } }).query.cursor;
      return cursor
        ? {
            body: {
              items: [app({ id: "a3", title: "Third" })],
              next_cursor: null,
            },
          }
        : {
            body: {
              items: [
                app({ id: "a1", status: "submitted" }),
                app({
                  id: "a2",
                  title: "Second",
                  status: "skipped",
                  skip_reason: "captcha",
                }),
              ],
              next_cursor: "c2",
            },
          };
    };
    renderWithProviders(<ApplicationList />);
    await screen.findByRole("link", { name: /Second/ });
    const list = screen.getByRole("list", { name: "Applications" });
    expect(within(list).getByText("Submitted")).toBeInTheDocument();
    expect(within(list).getByText("Skipped")).toBeInTheDocument();
    expect(within(list).getByText(/CAPTCHA/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByRole("link", { name: /Third/ })).toHaveAttribute(
      "href",
      "/applications/a3",
    );
    expect(
      screen.queryByRole("button", { name: "Load more" }),
    ).not.toBeInTheDocument();
  });

  it("filters by status", async () => {
    routes["GET /applications"] = () => ({
      body: { items: [], next_cursor: null },
    });
    renderWithProviders(<ApplicationList />);
    await screen.findByText("No applications yet");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "failed");
    expect(
      await screen.findByText("No failed applications"),
    ).toBeInTheDocument();
    expect(callsTo("GET /applications").at(-1)?.params).toEqual({
      query: { status: "failed", cursor: undefined, limit: 20 },
    });
  });

  it("shows an error with retry", async () => {
    routes["GET /applications"] = () => err(500, "server_error", "Down");
    renderWithProviders(<ApplicationList />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Down");
  });
});

describe("ApplicationDetail", () => {
  it("shows a skipped application with reason, direct link and retry", async () => {
    routes["GET /applications/{application_id}"] = () => ({
      body: app({
        status: "skipped",
        skip_reason: "site_not_opted_in",
        submitted_at: null,
      }),
    });
    routes["POST /runs/{run_id}/apply"] = () => err(409, "site_not_opted_in");
    renderWithProviders(<ApplicationDetail id="a1" />);
    expect(await screen.findByText(/haven.t opted in/i)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Apply yourself/ }),
    ).toHaveAttribute("href", "https://acme.example/apply");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Opt in to this site/,
    );
  });

  it("lists answers used and screenshot links", async () => {
    routes["GET /applications/{application_id}"] = () => ({
      body: app({
        answers_used: [
          {
            key: "email",
            label: "Email",
            required: true,
            source: "profile",
            value: "a@b.co",
          },
        ],
        screenshots: ["https://api.example/files/abc"],
      }),
    });
    renderWithProviders(<ApplicationDetail id="a1" />);
    expect(await screen.findByText("Email")).toBeInTheDocument();
    expect(screen.getByText("a@b.co")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Screenshot 1/ })).toHaveAttribute(
      "href",
      "https://api.example/files/abc",
    );
  });

  it("answers pending fields and keeps the input when the call fails", async () => {
    const pending = [
      {
        key: "years",
        label: "Years of experience",
        kind: "text",
        field_type: "number",
        options: [],
      },
      {
        key: "auth",
        label: "Work authorisation",
        kind: "select",
        field_type: "choice",
        options: ["Yes", "No"],
      },
    ];
    routes["GET /applications/{application_id}"] = () => ({
      body: app({
        status: "waiting_for_user",
        pending_fields: pending,
        submitted_at: null,
      }),
    });
    routes["POST /applications/{application_id}/answer"] = () =>
      err(409, "invalid_state");
    renderWithProviders(<ApplicationDetail id="a1" />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Send answers/ }),
    );
    expect(await screen.findAllByText("This field is required.")).toHaveLength(
      2,
    );
    await userEvent.type(screen.getByLabelText("Years of experience"), "6");
    await userEvent.selectOptions(
      screen.getByLabelText("Work authorisation"),
      "Yes",
    );
    await userEvent.click(screen.getByRole("button", { name: /Send answers/ }));
    expect(
      await screen.findByText(/changed in the meantime/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Years of experience")).toHaveValue("6");
    expect(
      callsTo("POST /applications/{application_id}/answer")[0].body,
    ).toEqual({
      answers: [
        { key: "years", value: "6", remember: true },
        { key: "auth", value: "Yes", remember: true },
      ],
    });
  });

  it("confirms before cancelling a running application", async () => {
    routes["GET /applications/{application_id}"] = () => ({
      body: app({ status: "running", submitted_at: null }),
    });
    routes["POST /applications/{application_id}/cancel"] = () => ({
      body: app({
        status: "cancelled",
        skip_reason: "user_cancelled",
        submitted_at: null,
      }),
    });
    renderWithProviders(<ApplicationDetail id="a1" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Cancel application" }),
    );
    expect(callsTo("POST /applications/{application_id}/cancel")).toHaveLength(
      0,
    );
    const buttons = screen.getAllByRole("button", {
      name: "Cancel application",
    });
    await userEvent.click(buttons[buttons.length - 1]);
    await waitFor(() =>
      expect(screen.getAllByText("Cancelled").length).toBeGreaterThan(0),
    );
    expect(callsTo("POST /applications/{application_id}/cancel")).toHaveLength(
      1,
    );
  });

  it("shows not-found without a retry button", async () => {
    routes["GET /applications/{application_id}"] = () => err(404, "not_found");
    renderWithProviders(<ApplicationDetail id="nope" />);
    expect(
      await screen.findByText("Application not found"),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Try again" }),
    ).not.toBeInTheDocument();
  });
});

describe("ApplyRun", () => {
  it("applies and goes to the application", async () => {
    routes["POST /runs/{run_id}/apply"] = () => ({
      status: 202,
      body: app({ id: "new1" }),
    });
    renderWithProviders(<ApplyRun runId="r1" />);
    await userEvent.click(screen.getByRole("button", { name: "Apply now" }));
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/applications/new1"),
    );
  });

  it("explains a run that is not approved", async () => {
    routes["POST /runs/{run_id}/apply"] = () => err(409, "run_not_approved");
    renderWithProviders(<ApplyRun runId="r1" />);
    await userEvent.click(screen.getByRole("button", { name: "Apply now" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Approve this resume/,
    );
  });
});
