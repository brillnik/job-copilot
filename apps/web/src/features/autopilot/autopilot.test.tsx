import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/features/common/test-utils";
import { callsTo, err, resetApi, routes } from "@/features/common/fake-api";
import { AutopilotSettings } from "./autopilot-settings";
import { DigestView } from "./digest-view";

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

const state = (over = {}) => ({
  enabled: false,
  min_score: 75,
  daily_apply_cap: 15,
  digest_time: "19:00",
  sites_opt_in: {
    wellfound: { acknowledged: false },
    naukri: { acknowledged: false },
    hiring_cafe: { acknowledged: false },
  },
  policy_version: "2026-11",
  acknowledged_version: null,
  paused_sites: [],
  ...over,
});

beforeEach(resetApi);

describe("AutopilotSettings", () => {
  it("is off by default and explains what it does", async () => {
    routes["GET /autopilot"] = () => ({ body: state() });
    renderWithProviders(<AutopilotSettings />);
    const status = await screen.findByRole("region", { name: "Autopilot" });
    expect(within(status).getByText("Off")).toBeInTheDocument();
    expect(
      screen.getByText(/never solves CAPTCHAs/i, { selector: "li" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText(/your own browser extension/i).length,
    ).toBeGreaterThan(0);
  });

  it("needs the acknowledgement before turning on and sends the policy version", async () => {
    routes["GET /autopilot"] = () => ({ body: state() });
    routes["PUT /autopilot"] = () => ({
      body: state({ enabled: true, acknowledged_version: "2026-11" }),
    });
    renderWithProviders(<AutopilotSettings />);
    const on = await screen.findByRole("button", { name: "Turn on Autopilot" });
    expect(on).toBeDisabled();
    await userEvent.click(
      screen.getByRole("checkbox", { name: /applies to jobs on my behalf/i }),
    );
    await userEvent.click(on);
    expect(
      await screen.findByRole("button", { name: "Turn off Autopilot" }),
    ).toBeInTheDocument();
    expect(callsTo("PUT /autopilot")[0].body).toEqual({
      enabled: true,
      acknowledgement_version: "2026-11",
    });
  });

  it("maps acknowledgement_required to human copy", async () => {
    routes["GET /autopilot"] = () => ({ body: state() });
    routes["PUT /autopilot"] = () => err(422, "acknowledgement_required");
    renderWithProviders(<AutopilotSettings />);
    await userEvent.click(
      await screen.findByRole("checkbox", { name: /applies to jobs/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Turn on Autopilot" }),
    );
    expect(await screen.findByText(/policy was updated/i)).toBeInTheDocument();
  });

  it("each site has its own risk text and its own acknowledgement", async () => {
    routes["GET /autopilot"] = () => ({ body: state() });
    routes["PUT /autopilot"] = () => ({
      body: state({
        sites_opt_in: {
          wellfound: {
            acknowledged: true,
            acknowledged_at: "2026-11-19T00:00:00Z",
            policy_version: "2026-11",
          },
          naukri: { acknowledged: false },
          hiring_cafe: { acknowledged: false },
        },
      }),
    });
    renderWithProviders(<AutopilotSettings />);
    const wf = await screen.findByRole("region", { name: "Wellfound" });
    const nk = screen.getByRole("region", { name: "Naukri" });
    expect(within(wf).getByText(/terms/i)).toBeInTheDocument();
    expect(
      within(nk).getByRole("button", { name: "Opt in to Naukri" }),
    ).toBeDisabled();
    await userEvent.click(within(wf).getByRole("checkbox"));
    await userEvent.click(
      within(wf).getByRole("button", { name: "Opt in to Wellfound" }),
    );
    expect(callsTo("PUT /autopilot")[0].body).toEqual({
      sites: {
        wellfound: { opt_in: true, acknowledgement_version: "2026-11" },
      },
    });
    expect(
      await within(
        screen.getByRole("region", { name: "Wellfound" }),
      ).findByText("Opted in"),
    ).toBeInTheDocument();
    // Naukri stays off: acknowledging one site never covers another.
    expect(
      screen.getByRole("button", { name: "Opt in to Naukri" }),
    ).toBeDisabled();
  });

  it("offers Resume for a paused site", async () => {
    routes["GET /autopilot"] = () => ({
      body: state({
        sites_opt_in: {
          wellfound: {
            acknowledged: true,
            paused: true,
            acknowledged_at: "2026-11-19T00:00:00Z",
          },
          naukri: { acknowledged: false },
          hiring_cafe: { acknowledged: false },
        },
        paused_sites: ["wellfound"],
      }),
    });
    routes["PUT /autopilot"] = () => ({ body: state() });
    renderWithProviders(<AutopilotSettings />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Resume Wellfound" }),
    );
    expect(callsTo("PUT /autopilot")[0].body).toEqual({
      resume_sites: ["wellfound"],
    });
  });

  it("validates rules and keeps what was typed when the save fails", async () => {
    routes["GET /autopilot"] = () => ({ body: state() });
    routes["PUT /autopilot"] = () => err(422, "validation_error");
    renderWithProviders(<AutopilotSettings />);
    const score = await screen.findByLabelText("Minimum match score");
    await userEvent.clear(score);
    await userEvent.type(score, "150");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText(/0 to 100/)).toBeInTheDocument();
    expect(callsTo("PUT /autopilot")).toHaveLength(0);
    await userEvent.clear(score);
    await userEvent.type(score, "80");
    await userEvent.click(screen.getByRole("button", { name: "Save rules" }));
    expect(await screen.findByText(/out of range/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Minimum match score")).toHaveValue(80);
    expect(callsTo("PUT /autopilot")[0].body).toEqual({
      min_score: 80,
      daily_apply_cap: 15,
      digest_time: "19:00",
    });
  });
});

describe("DigestView", () => {
  it("lists submitted, needs-a-person and skipped with reasons and direct links", async () => {
    routes["GET /autopilot/digest"] = () => ({
      body: {
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
        needs_a_person: [
          {
            application_id: "a2",
            job_id: "j2",
            company: "Beta",
            title: "FE",
            status: "waiting_for_user",
            reason: "required_field_no_value",
            direct_link: "https://b.example/apply",
          },
        ],
        skipped: [
          {
            application_id: "a3",
            job_id: "j3",
            company: "Gamma",
            title: "BE",
            status: "skipped",
            reason: "captcha",
            direct_link: "https://g.example/apply",
          },
        ],
      },
    });
    renderWithProviders(<DigestView />);
    const skipped = await screen.findByRole("region", { name: /Skipped/ });
    expect(within(skipped).getByText(/CAPTCHA/)).toBeInTheDocument();
    expect(
      within(skipped).getByRole("link", { name: /Apply yourself/ }),
    ).toHaveAttribute("href", "https://g.example/apply");
    expect(
      within(screen.getByRole("region", { name: /Submitted/ })).getByText(
        "SWE",
        { exact: false, selector: "p" },
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: /Needs a person/ })).getByText(
        /no saved answer/i,
      ),
    ).toBeInTheDocument();
  });

  it("shows empty sections and an error with retry", async () => {
    routes["GET /autopilot/digest"] = () => err(500, "server_error", "Nope");
    renderWithProviders(<DigestView />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nope");
    routes["GET /autopilot/digest"] = () => ({
      body: {
        date: "2026-11-19",
        submitted: [],
        skipped: [],
        needs_a_person: [],
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByText("Nothing was submitted on this day."),
    ).toBeInTheDocument();
  });
});
