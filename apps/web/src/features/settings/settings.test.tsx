import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

const GET = vi.fn();
const PUT = vi.fn();
const POST = vi.fn();
const DELETE = vi.fn();
vi.mock("@/lib/api/browser", () => ({
  api: {
    GET: (...a: unknown[]) => GET(...a),
    PUT: (...a: unknown[]) => PUT(...a),
    POST: (...a: unknown[]) => POST(...a),
    DELETE: (...a: unknown[]) => DELETE(...a),
  },
}));
vi.mock("@/providers/theme-provider", () => ({
  useTheme: () => ({ theme: "system", setTheme: () => {}, resolved: "light" }),
}));

import { ToastProvider } from "@/components/ui/toast";
import type { SettingsOut } from "@/hooks/use-settings";
import { settingsKey } from "@/hooks/use-settings";
import { AccountSection } from "./account-section";
import { downloadHref, reauthUrl } from "./api";
import { DeviceList } from "./devices-section";
import { PreferencesForm } from "./preferences-form";
import { preferencesSchema, toFormValues, toPreferences } from "./schema";

const settings: SettingsOut = {
  preferences: {
    target_roles: ["Frontend Engineer"],
    cities: ["Bengaluru"],
    current_ctc_lpa: 18,
    expected_ctc_lpa: 28,
    notice_days: 30,
    default_length: "auto",
    template: "classic",
    daily_cap: 5,
    coverage_target: 0.8,
    theme: "dark",
  },
  configured: true,
  rev: 4,
  runs_used_today: 2,
  daily_cap: 5,
  cap_resets_at: "2026-01-02T00:00:00Z",
};

function wrap(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  qc.setQueryData(settingsKey, settings);
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>{ui}</ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  [GET, PUT, POST, DELETE].forEach((m) => m.mockReset());
});

describe("schema", () => {
  it("mirrors the server bounds", () => {
    const ok = toFormValues(settings.preferences as never);
    expect(preferencesSchema.safeParse(ok).success).toBe(true);
    for (const bad of [
      { notice_days: 181 },
      { current_ctc_lpa: 501 },
      { daily_cap: 0 },
      { daily_cap: 51 },
      { target_roles: [] },
      { target_roles: Array(11).fill("x") },
      { cities: ["Atlantis"] },
      { coverage_target: "0.9" },
    ])
      expect(preferencesSchema.safeParse({ ...ok, ...bad }).success).toBe(false);
  });

  it("converts form values back to the API shape and keeps the account theme", () => {
    const v = toFormValues({ ...settings.preferences, default_length: 2 } as never);
    expect(v.default_length).toBe("2");
    expect(toPreferences(v, "dark")).toMatchObject({ default_length: 2, coverage_target: 0.8, theme: "dark" });
  });
});

describe("downloadHref / reauthUrl", () => {
  it("routes signed links through the same-origin proxy", () => {
    expect(downloadHref("http://api.invalid/files/tok.en")).toBe("/api/files/tok.en");
  });
  it("re-login forces a fresh sign-in and returns to settings", () => {
    const u = new URL(reauthUrl(), "http://x");
    expect(u.pathname).toBe("/auth/login");
    expect(u.searchParams.get("prompt")).toBe("login");
    expect(u.searchParams.get("max_age")).toBe("0");
    expect(u.searchParams.get("returnTo")).toBe("/settings?delete=1");
  });
});

describe("PreferencesForm", () => {
  it("shows used-today, blocks invalid input client-side and is axe-clean", async () => {
    const { container } = wrap(<PreferencesForm settings={settings} />);
    expect(screen.getByText("2 of 5")).toBeVisible();
    const user = userEvent.setup();
    const notice = screen.getByLabelText("Notice period (days)");
    await user.clear(notice);
    await user.type(notice, "400");
    await user.click(screen.getByRole("button", { name: "Save preferences" }));
    expect(await screen.findByText("At most 180 days")).toBeVisible();
    expect(PUT).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("saves the full body with the revision as If-Match", async () => {
    PUT.mockResolvedValue({ data: { ...settings, rev: 5 }, response: new Response() });
    wrap(<PreferencesForm settings={settings} />);
    const user = userEvent.setup();
    await user.click(screen.getByLabelText("Pune"));
    await user.click(screen.getByRole("button", { name: "Save preferences" }));
    await waitFor(() => expect(PUT).toHaveBeenCalled());
    expect(PUT.mock.calls[0][1].params.header).toEqual({ "if-match": '"4"' });
    expect(PUT.mock.calls[0][1].body).toMatchObject({ cities: ["Bengaluru", "Pune"], theme: "dark", coverage_target: 0.8 });
    expect(await screen.findByText("Preferences saved.")).toBeVisible();
  });

  it("keeps the user's input and offers choices on a stale write", async () => {
    PUT.mockResolvedValue({
      error: { code: "stale_write", message: "stale" },
      response: new Response(null, { status: 409 }),
    });
    wrap(<PreferencesForm settings={settings} />);
    const user = userEvent.setup();
    const notice = screen.getByLabelText("Notice period (days)");
    await user.clear(notice);
    await user.type(notice, "60");
    await user.click(screen.getByRole("button", { name: "Save preferences" }));
    expect(await screen.findByRole("button", { name: "Save my changes anyway" })).toBeVisible();
    expect(notice).toHaveValue(60);
  });
});

describe("DeviceList", () => {
  it("lists active devices, hides revoked ones and revokes by name", async () => {
    const onRevoke = vi.fn();
    render(
      <DeviceList
        onRevoke={onRevoke}
        devices={[
          { id: "a", device_name: "Chrome on Mac", created_at: "2026-01-01T00:00:00Z", last_used_at: null, revoked_at: null },
          { id: "b", device_name: "Old laptop", created_at: "2026-01-01T00:00:00Z", last_used_at: null, revoked_at: "2026-01-02T00:00:00Z" },
        ]}
      />,
    );
    expect(screen.queryByText("Old laptop")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Revoke Chrome on Mac" }));
    expect(onRevoke).toHaveBeenCalledWith(expect.objectContaining({ id: "a" }));
  });
});

describe("AccountSection", () => {
  it("needs DELETE typed and prompts re-auth on 401 reauth_required", async () => {
    DELETE.mockResolvedValue({
      error: { code: "reauth_required", message: "Sign in again" },
      response: new Response(null, { status: 401 }),
    });
    wrap(<AccountSection />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Delete my account" }));
    const go = screen.getByRole("button", { name: "Delete account" });
    expect(go).toBeDisabled();
    await user.type(screen.getByLabelText("Type DELETE to confirm"), "DELETE");
    await user.click(go);
    expect(await screen.findByRole("button", { name: "Sign in again" })).toBeVisible();
    expect(DELETE.mock.calls[0][1]).toEqual({ body: { confirm: "DELETE" } });
  });
});
