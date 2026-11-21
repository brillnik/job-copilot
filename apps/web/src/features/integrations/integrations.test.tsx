import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/features/common/test-utils";
import { callsTo, err, resetApi, routes } from "@/features/common/fake-api";
import { GmailSection } from "@/features/gmail/gmail-section";
import { ScreeningAnswers } from "@/features/screening/screening-answers";
import { ExtensionSection } from "./extension-section";
import { PairCodeCard, formatClock } from "./pair-code-card";
import { TRAINING_POLICY_VERSION, TrainingConsent } from "./training-consent";

vi.mock("@/lib/api/browser", async () => ({
  api: (await import("@/features/common/fake-api")).fakeClient,
}));

beforeEach(resetApi);

describe("PairCodeCard", () => {
  afterEach(() => vi.useRealTimers());

  it("counts down and announces expiry through the live region", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-19T10:00:00Z"));
    render(<PairCodeCard code="ABCD-EFGH" expiresAt="2026-11-19T10:00:03Z" />);
    expect(screen.getByText("ABCD-EFGH")).toBeInTheDocument();
    expect(screen.getByText("0:03")).toBeInTheDocument();
    const live = screen.getByRole("status");
    expect(live).toHaveTextContent("");
    act(() => void vi.advanceTimersByTime(3500));
    expect(screen.getByText("This code has expired.")).toBeInTheDocument();
    expect(live).toHaveTextContent("Code expired");
    expect(screen.getByRole("button", { name: "Copy code" })).toBeDisabled();
  });

  it("copies the code and says so", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
    render(
      <PairCodeCard
        code="ABCD-EFGH"
        expiresAt={new Date(Date.now() + 600_000).toISOString()}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Copy code" }));
    expect(writeText).toHaveBeenCalledWith("ABCD-EFGH");
    expect(screen.getByRole("status")).toHaveTextContent("Code copied.");
  });

  it("formats the clock", () => {
    expect(formatClock(600)).toBe("10:00");
    expect(formatClock(65)).toBe("1:05");
  });
});

describe("ExtensionSection", () => {
  it("gets a code, lists devices and revokes one after confirming", async () => {
    routes["POST /extension/pair-code"] = () => ({
      body: {
        code: "WXYZ-1234",
        expires_at: new Date(Date.now() + 600_000).toISOString(),
      },
    });
    let revoked = false;
    routes["GET /extension/tokens"] = () => ({
      body: [
        {
          id: "t1",
          device_name: "Chrome on Mac",
          created_at: "2026-11-01T00:00:00Z",
          last_used_at: null,
          revoked_at: revoked ? "2026-11-19T00:00:00Z" : null,
        },
        {
          id: "t2",
          device_name: "Old laptop",
          created_at: "2026-10-01T00:00:00Z",
          last_used_at: null,
          revoked_at: "2026-10-02T00:00:00Z",
        },
      ],
    });
    routes["DELETE /extension/tokens/{token_id}"] = () => {
      revoked = true;
      return { status: 204 };
    };
    renderWithProviders(<ExtensionSection />);
    await userEvent.click(
      screen.getByRole("button", { name: "Get a pairing code" }),
    );
    expect(await screen.findByText("WXYZ-1234")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Paired devices" });
    expect(within(list).getByText("Chrome on Mac", { selector: "p" })).toBeInTheDocument();
    expect(screen.getAllByText(/^Revoked/)).toHaveLength(1);
    await userEvent.click(
      screen.getByRole("button", { name: /Revoke Chrome on Mac/ }),
    );
    expect(callsTo("DELETE /extension/tokens/{token_id}")).toHaveLength(0);
    await userEvent.click(
      screen.getByRole("button", { name: "Revoke device" }),
    );
    await waitFor(() =>
      expect(screen.getAllByText(/^Revoked/)).toHaveLength(2),
    );
  });
});

const ans = (id: string, over = {}) => ({
  id,
  question: `Question ${id}`,
  answer: `Answer ${id}`,
  field_type: "text",
  source: "user",
  updated_at: "2026-11-01T00:00:00Z",
  ...over,
});

describe("ScreeningAnswers", () => {
  it("lists, edits (keeping input on failure) and deletes", async () => {
    routes["GET /screening-answers"] = () => ({
      body: { items: [ans("1"), ans("2")] },
    });
    renderWithProviders(<ScreeningAnswers />);
    expect(await screen.findByText("Question 1")).toBeInTheDocument();

    routes["PUT /screening-answers/{answer_id}"] = () =>
      err(422, "validation_error");
    await userEvent.click(
      screen.getByRole("button", { name: /Edit answer: Question 1/ }),
    );
    const box = screen.getByLabelText("Answer");
    await userEvent.clear(box);
    await userEvent.type(box, "New text");
    await userEvent.click(screen.getByRole("button", { name: "Save answer" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByLabelText("Answer")).toHaveValue("New text");

    routes["PUT /screening-answers/{answer_id}"] = ({ body }) => ({
      body: ans("1", {
        answer: (body as { answer: string }).answer,
        source: "user",
      }),
    });
    await userEvent.click(screen.getByRole("button", { name: "Save answer" }));
    expect(await screen.findByText("New text")).toBeInTheDocument();
    expect(callsTo("PUT /screening-answers/{answer_id}").at(-1)?.body).toEqual({
      answer: "New text",
      question: null,
    });

    routes["DELETE /screening-answers/{answer_id}"] = () => ({ status: 204 });
    await userEvent.click(
      screen.getByRole("button", { name: /Delete answer: Question 2/ }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Delete answer" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("Question 2")).not.toBeInTheDocument(),
    );
  });

  it("shows the empty state", async () => {
    routes["GET /screening-answers"] = () => ({ body: { items: [] } });
    renderWithProviders(<ScreeningAnswers />);
    expect(await screen.findByText("No saved answers yet")).toBeInTheDocument();
  });
});

const sugg = (over = {}) => ({
  id: "s1",
  job_id: "j1",
  company: "Acme",
  title: "SWE",
  classification: "interview_invite",
  confidence: 0.91,
  suggested_column: "interview",
  status: "pending",
  received_at: "2026-11-19T00:00:00Z",
  ...over,
});

describe("GmailSection", () => {
  it("is hidden entirely when the feature is off", async () => {
    routes["GET /integrations/gmail"] = () => ({
      body: { enabled: false, connected: false },
    });
    const { container } = renderWithProviders(<GmailSection />);
    await waitFor(() =>
      expect(callsTo("GET /integrations/gmail")).toHaveLength(1),
    );
    await waitFor(() => expect(container.querySelector("section")).toBeNull());
  });

  it("redirects the browser to Google's consent URL when connecting", async () => {
    routes["GET /integrations/gmail"] = () => ({
      body: { enabled: true, connected: false },
    });
    routes["GET /integrations/gmail/connect"] = () => ({
      body: { url: "https://accounts.google.com/o/oauth2/x" },
    });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    renderWithProviders(<GmailSection />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Connect Gmail" }),
    );
    await waitFor(() =>
      expect(assign).toHaveBeenCalledWith(
        "https://accounts.google.com/o/oauth2/x",
      ),
    );
    vi.unstubAllGlobals();
  });

  it("shows 'Move X to Interview?' and confirms", async () => {
    let pending = true;
    routes["GET /integrations/gmail"] = () => ({
      body: {
        enabled: true,
        connected: true,
        pending_suggestions: pending ? 1 : 0,
        connected_at: "2026-11-01T00:00:00Z",
      },
    });
    routes["GET /integrations/gmail/suggestions"] = () => ({
      body: pending ? [sugg()] : [sugg({ status: "accepted" })],
    });
    routes["POST /integrations/gmail/suggestions/{suggestion_id}/accept"] =
      () => {
        pending = false;
        return { body: sugg({ status: "accepted" }) };
      };
    renderWithProviders(<GmailSection />);
    expect(
      await screen.findByRole("heading", { name: "Move Acme to Interview?" }),
    ).toBeInTheDocument();
    expect(screen.getByText("91% sure")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Confirm/ }));
    expect(
      await screen.findByText(/No suggestions waiting/),
    ).toBeInTheDocument();
  });

  it("explains an already-resolved suggestion", async () => {
    routes["GET /integrations/gmail"] = () => ({
      body: { enabled: true, connected: true },
    });
    routes["GET /integrations/gmail/suggestions"] = () => ({ body: [sugg()] });
    routes["POST /integrations/gmail/suggestions/{suggestion_id}/dismiss"] =
      () => err(409, "already_resolved");
    renderWithProviders(<GmailSection />);
    await userEvent.click(
      await screen.findByRole("button", { name: /Dismiss/ }),
    );
    expect(await screen.findByText(/already handled/i)).toBeInTheDocument();
  });

  it("flags needs_reconnect and confirms before disconnecting", async () => {
    routes["GET /integrations/gmail"] = () => ({
      body: { enabled: true, connected: true, needs_reconnect: true },
    });
    routes["DELETE /integrations/gmail"] = () => ({ status: 204 });
    renderWithProviders(<GmailSection />);
    expect(
      await screen.findByRole("button", { name: "Reconnect Gmail" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(/stopped accepting/);
    await userEvent.click(
      screen.getByRole("button", { name: "Disconnect Gmail" }),
    );
    const dialog = screen.getByRole("dialog", { hidden: true });
    expect(
      within(dialog).getByText(/delete the connection and every email event/),
    ).toBeInTheDocument();
    expect(callsTo("DELETE /integrations/gmail")).toHaveLength(0);
    await userEvent.click(
      within(dialog).getByRole("button", {
        name: "Disconnect and delete",
        hidden: true,
      }),
    );
    await waitFor(() =>
      expect(callsTo("DELETE /integrations/gmail")).toHaveLength(1),
    );
  });
});

describe("TrainingConsent", () => {
  it("is a switch, off by default, and sends the policy version", async () => {
    let enabled = false;
    routes["GET /me/training-consent"] = () => ({ body: { enabled } });
    routes["PUT /me/training-consent"] = ({ body }) => {
      enabled = (body as { enabled: boolean }).enabled;
      return {
        body: {
          enabled,
          policy_version: TRAINING_POLICY_VERSION,
          at: "2026-11-19T00:00:00Z",
        },
      };
    };
    renderWithProviders(<TrainingConsent />);
    const sw = await screen.findByRole("switch");
    expect(sw).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText(/future/)).toBeInTheDocument();
    await userEvent.click(sw);
    await waitFor(() =>
      expect(screen.getByRole("switch")).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
    expect(callsTo("PUT /me/training-consent")[0].body).toEqual({
      enabled: true,
      policy_version: TRAINING_POLICY_VERSION,
    });
    expect(screen.getByRole("status")).toHaveTextContent("sharing is on");
  });

  it("shows an error with retry when it can't load", async () => {
    routes["GET /me/training-consent"] = () => err(500, "server_error", "Nope");
    renderWithProviders(<TrainingConsent />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nope");
  });
});
