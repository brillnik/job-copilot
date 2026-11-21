import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/browser", async () => ({ api: (await import("./test-support")).apiMock }));
vi.mock("next/navigation", async () => {
  const { router } = await import("./test-support");
  return { useRouter: () => router };
});

import { clearConsentTick, rememberConsentTick } from "@/lib/policy";
import { ConsentStep } from "./consent-step";
import { apiMock, fail, ok, renderWithClient, router } from "./test-support";

const me = (consent: unknown) =>
  ok({ id: "u", email: "a@b.co", name: "A", auth_providers: [], consent, created_at: "x", plan: "free" });

describe("ConsentStep", () => {
  beforeEach(() => {
    Object.values(apiMock).forEach((m) => m.mockReset());
    router.replace.mockReset();
    clearConsentTick();
  });

  it("requires the box, then records the policy version", async () => {
    apiMock.GET.mockResolvedValue(me(null));
    apiMock.POST.mockResolvedValue(ok({ policy_version: "2026-01", at: "x" }));
    renderWithClient(<ConsentStep />);
    const go = await screen.findByRole("button", { name: "Agree and continue" });
    expect(go).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(go);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    expect(apiMock.POST).toHaveBeenCalledWith("/me/consent", { body: { policy_version: "2026-01" } });
  });

  it("records straight away when the sign-in box was already ticked", async () => {
    rememberConsentTick();
    apiMock.GET.mockResolvedValue(me(null));
    apiMock.POST.mockResolvedValue(ok({ policy_version: "2026-01", at: "x" }));
    renderWithClient(<ConsentStep />);
    await waitFor(() => expect(apiMock.POST).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
  });

  it("falls back to the explicit box with retry if recording fails", async () => {
    rememberConsentTick();
    apiMock.GET.mockResolvedValue(me(null));
    apiMock.POST.mockResolvedValue(fail(500, { code: "server_error", message: "Boom" }));
    renderWithClient(<ConsentStep />);
    expect(await screen.findByText("Couldn't record your consent")).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeInTheDocument();
  });

  it("skips ahead when consent already exists", async () => {
    apiMock.GET.mockResolvedValue(me({ policy_version: "2026-01", at: "x" }));
    renderWithClient(<ConsentStep />);
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/"));
    expect(apiMock.POST).not.toHaveBeenCalled();
  });
});
