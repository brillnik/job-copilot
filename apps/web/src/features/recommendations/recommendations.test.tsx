import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/features/common/test-utils";
import { callsTo, err, resetApi, routes } from "@/features/common/fake-api";
import { ForYou } from "./for-you";

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

const rec = (id: string, over = {}) => ({
  id,
  catalog_job_id: `c${id}`,
  score: 86,
  reasons: ["Skills match: React, TypeScript", "Salary above your expectation"],
  digest_date: "2026-11-19",
  action: "none",
  job_id: null,
  title: `Role ${id}`,
  company: "Acme",
  location: "Bengaluru",
  remote: true,
  apply_url: "https://example.com/apply",
  source_attribution: null,
  ...over,
});

beforeEach(resetApi);

describe("ForYou", () => {
  it("shows score as a number plus the reasons verbatim", async () => {
    routes["GET /recommendations"] = () => ({
      body: { items: [rec("1"), rec("2", { score: 41 })] },
    });
    renderWithProviders(<ForYou />);
    const card = await screen.findByRole("article", { name: "Role 1" });
    expect(within(card).getByText("86")).toBeInTheDocument();
    expect(
      within(card).getByText("Skills match: React, TypeScript"),
    ).toBeInTheDocument();
    expect(within(card).getByRole("meter")).toHaveAttribute(
      "aria-valuenow",
      "86",
    );
    expect(
      within(screen.getByRole("article", { name: "Role 2" })).getByText("41"),
    ).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    routes["GET /recommendations"] = () => ({ body: { items: [] } });
    renderWithProviders(<ForYou />);
    expect(
      await screen.findByText("Nothing new for you today"),
    ).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    routes["GET /recommendations"] = () => err(500, "server_error", "Boom");
    renderWithProviders(<ForYou />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Boom");
    routes["GET /recommendations"] = () => ({ body: { items: [rec("1")] } });
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("article", { name: "Role 1" }),
    ).toBeInTheDocument();
  });

  it("saves and then offers the saved job", async () => {
    routes["GET /recommendations"] = () => ({ body: { items: [rec("1")] } });
    routes["POST /recommendations/{rec_id}/save"] = () => ({
      body: rec("1", { action: "saved", job_id: "j9" }),
    });
    renderWithProviders(<ForYou />);
    await userEvent.click(await screen.findByRole("button", { name: /Save/ }));
    const link = await screen.findByRole("link", { name: "Open saved job" });
    expect(link).toHaveAttribute("href", "/jobs/j9");
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("dismisses with a reason and removes the card", async () => {
    routes["GET /recommendations"] = () => ({
      body: { items: [rec("1"), rec("2")] },
    });
    routes["POST /recommendations/{rec_id}/dismiss"] = () => ({
      body: rec("1", { action: "dismissed" }),
    });
    renderWithProviders(<ForYou />);
    const card = await screen.findByRole("article", { name: "Role 1" });
    await userEvent.click(
      within(card).getByRole("button", { name: /Dismiss/ }),
    );
    await userEvent.type(screen.getByLabelText(/Reason/), "Too junior");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss role" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("article", { name: "Role 1" }),
      ).not.toBeInTheDocument(),
    );
    expect(callsTo("POST /recommendations/{rec_id}/dismiss")[0].body).toEqual({
      reason: "Too junior",
    });
  });

  it("keeps the dialog and the typed reason when dismiss fails", async () => {
    routes["GET /recommendations"] = () => ({ body: { items: [rec("1")] } });
    routes["POST /recommendations/{rec_id}/dismiss"] = () =>
      err(409, "invalid_state");
    renderWithProviders(<ForYou />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Dismiss/ }),
    );
    await userEvent.type(screen.getByLabelText(/Reason/), "Nope");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss role" }));
    expect(await screen.findByText(/already saved/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Reason/)).toHaveValue("Nope");
  });
});
