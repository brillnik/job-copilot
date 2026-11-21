import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const login = vi.fn();
vi.mock("./login", () => ({
  login: (...a: unknown[]) => login(...a),
  GOOGLE_CONNECTION: "google-oauth2",
  EMAIL_CONNECTION: undefined,
}));

import { clearConsentTick, hasConsentTick } from "@/lib/policy";
import { SignInForm } from "./sign-in-form";

describe("SignInForm", () => {
  beforeEach(() => {
    login.mockReset();
    clearConsentTick();
  });

  it("blocks both sign-in routes until the DPDP consent box is ticked", async () => {
    render(<SignInForm />);
    expect(screen.getByRole("button", { name: /continue with google/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /continue with email/i })).toBeDisabled();
    expect(login).not.toHaveBeenCalled();
    expect(hasConsentTick()).toBe(false);
  });

  it("Google: redirects with the google connection and remembers the tick for the consent step", async () => {
    render(<SignInForm />);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: /continue with google/i }));
    expect(login).toHaveBeenCalledWith({ connection: "google-oauth2" });
    expect(hasConsentTick()).toBe(true);
  });

  it("Email: validates the address, then redirects with it as login_hint", async () => {
    render(<SignInForm />);
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    expect(await screen.findByText("Enter your email")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText(/email/i), "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: /continue with email/i }));
    await waitFor(() => expect(login).toHaveBeenCalledWith({ login_hint: "me@example.com" }));
  });
});
