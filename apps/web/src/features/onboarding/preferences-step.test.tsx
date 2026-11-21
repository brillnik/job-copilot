import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/browser", async () => ({ api: (await import("./test-support")).apiMock }));
vi.mock("next/navigation", async () => {
  const { router } = await import("./test-support");
  return { useRouter: () => router };
});

import { ThemeProvider } from "@/providers/theme-provider";
import { PreferencesStep } from "./preferences-step";
import { apiMock, fail, ok, renderWithClient, router } from "./test-support";
import { validatePrefs, toPrefValues } from "./preferences-model";

const prefs = {
  target_roles: [],
  cities: [],
  current_ctc_lpa: 0,
  expected_ctc_lpa: 0,
  notice_days: 30,
  default_length: "auto",
  template: "classic",
  daily_cap: 5,
  coverage_target: 0.7,
  theme: "system",
};
const settings = (configured = false) =>
  ok(
    {
      preferences: prefs,
      configured,
      rev: 1,
      runs_used_today: 0,
      daily_cap: 5,
      cap_resets_at: "2026-01-02T00:00:00Z",
    },
    { etag: '"1"' },
  );
const view = () =>
  renderWithClient(
    <ThemeProvider>
      <PreferencesStep />
    </ThemeProvider>,
  );

describe("PreferencesStep", () => {
  beforeEach(() => {
    Object.values(apiMock).forEach((m) => m.mockReset());
    router.push.mockReset();
    apiMock.GET.mockResolvedValue(settings());
  });

  it("validates before sending anything", async () => {
    view();
    await screen.findByRole("button", { name: /save and go to inbox/i });
    await userEvent.click(screen.getByRole("button", { name: /save and go to inbox/i }));
    expect(screen.getByText("Add at least one role you're targeting")).toBeInTheDocument();
    expect(apiMock.PUT).not.toHaveBeenCalled();
  });

  it("saves a full-replace body with If-Match and goes to the inbox", async () => {
    apiMock.PUT.mockResolvedValue(
      ok({
        preferences: prefs,
        configured: true,
        rev: 2,
        runs_used_today: 0,
        daily_cap: 5,
        cap_resets_at: "2026-01-02T00:00:00Z",
      }),
    );
    view();
    await screen.findByRole("button", { name: /save and go to inbox/i });
    await userEvent.type(screen.getByLabelText("Roles you're targeting"), "Frontend Engineer{Enter}");
    expect(screen.getByRole("button", { name: "Remove Frontend Engineer" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Pune" }));
    await userEvent.clear(screen.getByLabelText("Current CTC (LPA)"));
    await userEvent.type(screen.getByLabelText("Current CTC (LPA)"), "18.5");
    await userEvent.type(screen.getByLabelText("Expected CTC (LPA)"), "28");
    await userEvent.click(screen.getByRole("radio", { name: "2 pages" }));
    await userEvent.click(screen.getByRole("radio", { name: "Compact" }));
    await userEvent.click(screen.getByRole("button", { name: /save and go to inbox/i }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/"));
    const [path, init] = apiMock.PUT.mock.calls[0];
    expect(path).toBe("/settings");
    expect(init.params.header["if-match"]).toBe('"1"');
    expect(init.body).toEqual({
      ...prefs,
      target_roles: ["Frontend Engineer"],
      cities: ["Pune"],
      current_ctc_lpa: 18.5,
      expected_ctc_lpa: 28,
      default_length: 2,
      template: "compact",
      theme: "system", // an unconfigured user keeps their local theme choice
    });
  });

  it("puts 422 messages on the field and keeps the input", async () => {
    apiMock.PUT.mockResolvedValue(
      fail(422, {
        code: "validation_error",
        message: "Request validation failed",
        details: [{ loc: ["body", "cities"], msg: "Value error, unknown city; allowed: Pune", type: "value_error" }],
      }),
    );
    view();
    await screen.findByRole("button", { name: /save and go to inbox/i });
    await userEvent.type(screen.getByLabelText("Roles you're targeting"), "SRE{Enter}");
    await userEvent.click(screen.getByRole("button", { name: /save and go to inbox/i }));
    expect(await screen.findByText("unknown city; allowed: Pune")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove SRE" })).toBeInTheDocument();
  });

  it("shows an error state with retry when settings fail to load", async () => {
    apiMock.GET.mockResolvedValue(fail(500, { code: "server_error", message: "Down" }));
    view();
    expect(await screen.findByText("Couldn't load your preferences")).toBeInTheDocument();
  });
});

describe("validatePrefs", () => {
  const base = toPrefValues({ ...prefs, target_roles: ["SWE"] } as never);
  it("checks CTC and notice ranges", () => {
    expect(validatePrefs(base)).toEqual({});
    expect(validatePrefs({ ...base, currentCtc: "501" }).currentCtc).toBeDefined();
    expect(validatePrefs({ ...base, expectedCtc: "" }).expectedCtc).toBeDefined();
    expect(validatePrefs({ ...base, noticeDays: "181" }).noticeDays).toBeDefined();
    expect(validatePrefs({ ...base, noticeDays: "1.5" }).noticeDays).toBeDefined();
  });
});
