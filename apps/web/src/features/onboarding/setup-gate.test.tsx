import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/browser", async () => ({ api: (await import("./test-support")).apiMock }));
vi.mock("next/navigation", async () => {
  const { router } = await import("./test-support");
  return { useRouter: () => router };
});

import { apiMock, fail, notFound, ok, profileOut, renderWithClient, router } from "./test-support";
import { SetupGate } from "./setup-gate";

type Scenario = { consent: boolean; approved: boolean; draft: boolean; configured: boolean };
function scenario(s: Scenario) {
  apiMock.GET.mockImplementation(async (path: string) => {
    if (path === "/me")
      return ok({ id: "u", email: null, name: null, auth_providers: [], created_at: "x", plan: "free", consent: s.consent ? { policy_version: "2026-01", at: "x" } : null });
    if (path === "/profile") return s.approved ? ok(profileOut({ status: "approved", version: 1 })) : notFound();
    if (path === "/profile/draft") return s.draft ? ok(profileOut()) : notFound();
    if (path === "/settings")
      return ok({ preferences: {}, configured: s.configured, rev: 1, runs_used_today: 0, daily_cap: 5, cap_resets_at: "x" });
    throw new Error(path);
  });
}
const base: Scenario = { consent: true, approved: true, draft: false, configured: true };
const view = () => renderWithClient(<SetupGate><p>the app</p></SetupGate>);

describe("SetupGate (post sign-in routing)", () => {
  beforeEach(() => {
    Object.values(apiMock).forEach((m) => m.mockReset());
    router.replace.mockReset();
  });
  it.each([
    ["no consent -> consent step", { ...base, consent: false }, "/onboarding/consent"],
    ["no approved profile -> upload", { ...base, approved: false }, "/onboarding/upload"],
    ["draft but not approved -> review", { ...base, approved: false, draft: true }, "/onboarding/review"],
    ["approved but no preferences -> preferences", { ...base, configured: false }, "/onboarding/preferences"],
  ])("%s", async (_n, s, path) => {
    scenario(s);
    view();
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith(path));
    expect(screen.queryByText("the app")).not.toBeInTheDocument();
  });
  it("renders the app once setup is complete", async () => {
    scenario(base);
    view();
    expect(await screen.findByText("the app")).toBeInTheDocument();
    expect(router.replace).not.toHaveBeenCalled();
  });
  it("shows a retryable error if the account can't load", async () => {
    apiMock.GET.mockResolvedValue(fail(500, { code: "server_error", message: "Down" }));
    view();
    expect(await screen.findByText("Couldn't load your account")).toBeInTheDocument();
  });
});
