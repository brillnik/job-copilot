import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/browser", async () => ({ api: (await import("./test-support")).apiMock }));
vi.mock("next/navigation", async () => {
  const { router } = await import("./test-support");
  return { useRouter: () => router };
});

import { apiMock, fail, notFound, ok, profileOut, renderWithClient, router } from "./test-support";
import { ReviewStep } from "./review-step";

const approveBtn = () => screen.getByRole("button", { name: "Approve and continue" });

describe("ReviewStep", () => {
  beforeEach(() => {
    Object.values(apiMock).forEach((m) => m.mockReset());
    router.push.mockReset();
    apiMock.GET.mockResolvedValue(ok(profileOut()));
  });

  it("blocks Continue until the flagged value is confirmed, then saves and approves", async () => {
    apiMock.PUT.mockResolvedValue(ok(profileOut()));
    apiMock.POST.mockResolvedValue(ok(profileOut({ status: "approved", version: 1 })));
    renderWithClient(<ReviewStep />);
    await screen.findByRole("heading", { name: "Check your profile" });
    // The draft has no end date: that is the one thing to confirm.
    expect(screen.getByText(/1 item needs your confirmation/)).toBeInTheDocument();
    expect(approveBtn()).toBeDisabled();
    expect(screen.getAllByText(/Missing: no end date/).length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("checkbox", { name: "This is my current role" }));
    expect(screen.getByText(/All items checked/)).toBeInTheDocument();
    expect(approveBtn()).toBeEnabled();

    await userEvent.click(approveBtn());
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/onboarding/preferences"));
    // Ids, links and blanks round-trip through PUT /profile/draft, then POST /profile/approve.
    const [path, init] = apiMock.PUT.mock.calls[0];
    expect(path).toBe("/profile/draft");
    expect(init.body.experience[0]).toMatchObject({ id: "e1", end: null, bullets: [{ id: "b1" }] });
    expect(init.body.contact.links).toEqual(["https://asha.dev"]);
    expect(apiMock.POST.mock.calls[0][0]).toBe("/profile/approve");
  });

  it("filling the missing value resolves the flag without a confirmation", async () => {
    renderWithClient(<ReviewStep />);
    await screen.findByRole("heading", { name: "Check your profile" });
    await userEvent.type(screen.getAllByLabelText("End")[0], "Present");
    expect(approveBtn()).toBeEnabled();
  });

  it("shows 422 messages on the right field and keeps the user's edits", async () => {
    apiMock.PUT.mockResolvedValue(
      fail(422, {
        code: "validation_error",
        message: "Request validation failed",
        details: [{ loc: ["body", "experience", 0, "bullets", 0, "text"], msg: "String should have at most 1000 characters", type: "string_too_long" }],
      }),
    );
    renderWithClient(<ReviewStep />);
    await screen.findByRole("heading", { name: "Check your profile" });
    await userEvent.click(screen.getByRole("checkbox", { name: "This is my current role" }));
    const bullet = screen.getByLabelText("Role 1 achievement 1");
    await userEvent.clear(bullet);
    await userEvent.type(bullet, "My edit");
    await userEvent.click(approveBtn());
    const field = await screen.findByLabelText("Role 1 achievement 1");
    await waitFor(() => expect(field).toHaveAttribute("aria-invalid", "true"));
    expect(field).toHaveValue("My edit");
    expect(within(field.parentElement!).getByText(/at most 1000/)).toBeInTheDocument();
    expect(apiMock.POST).not.toHaveBeenCalled();
  });

  it("offers a reload on a 409 conflict and loads the latest draft on request", async () => {
    apiMock.PUT.mockResolvedValue(fail(409, { code: "conflict", message: "Conflict" }));
    renderWithClient(<ReviewStep />);
    await screen.findByRole("heading", { name: "Check your profile" });
    await userEvent.click(screen.getByRole("checkbox", { name: "This is my current role" }));
    await userEvent.click(approveBtn());
    expect(await screen.findByText("This profile changed somewhere else")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByText("This profile changed somewhere else")).not.toBeInTheDocument());
  });

  it("keeps the form on a server error and can retry", async () => {
    apiMock.PUT.mockResolvedValueOnce(fail(500, { code: "server_error", message: "Boom" })).mockResolvedValue(ok(profileOut()));
    apiMock.POST.mockResolvedValue(ok(profileOut({ status: "approved", version: 1 })));
    renderWithClient(<ReviewStep />);
    await screen.findByRole("heading", { name: "Check your profile" });
    await userEvent.click(screen.getByRole("checkbox", { name: "This is my current role" }));
    await userEvent.click(approveBtn());
    expect(await screen.findByText("Couldn't save your profile")).toBeInTheDocument();
    expect(screen.getByLabelText("Company")).toHaveValue("Acme");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
  });

  it("shows an empty state when there is no draft", async () => {
    apiMock.GET.mockResolvedValue(notFound());
    renderWithClient(<ReviewStep />);
    expect(await screen.findByText("No draft to review")).toBeInTheDocument();
  });

  it("shows an error state with retry when the draft can't load", async () => {
    apiMock.GET.mockResolvedValue(fail(500, { code: "server_error", message: "Down" }));
    renderWithClient(<ReviewStep />);
    expect(await screen.findByText("Couldn't load your draft")).toBeInTheDocument();
  });
});
