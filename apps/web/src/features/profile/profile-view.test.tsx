import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/browser", async () => ({
  api: (await import("../onboarding/test-support")).apiMock,
}));

import {
  apiMock,
  fail,
  notFound,
  ok,
  profileOut,
  renderWithClient,
} from "../onboarding/test-support";
import { ProfileView } from "./profile-view";

const approved = () =>
  profileOut({
    status: "approved",
    version: 3,
    approved_at: "2026-02-01T00:00:00Z",
  });
function api(opts: {
  draft?: unknown;
  approved?: unknown;
  answers?: unknown[];
}) {
  apiMock.GET.mockImplementation(async (path: string) => {
    if (path === "/profile")
      return opts.approved === null
        ? notFound()
        : ok(opts.approved ?? approved());
    if (path === "/profile/draft")
      return opts.draft ? ok(opts.draft) : notFound();
    if (path === "/screening-answers") return ok({ items: opts.answers ?? [] });
    throw new Error(path);
  });
}

describe("ProfileView", () => {
  beforeEach(() => Object.values(apiMock).forEach((m) => m.mockReset()));

  it("shows the approved version, bullets with derived chips, and honest placeholders", async () => {
    api({});
    renderWithClient(<ProfileView />);
    expect(await screen.findByText("Approved · v3")).toBeInTheDocument();
    expect(
      screen.getByText("Cut p95 latency by 40% using React"),
    ).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("list", { name: "Numbers in the text" }),
      ).getByText("40%"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("list", { name: "Skills mentioned" })).getByText(
        "React",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Unapproved")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Unapproved changes" }),
    ).not.toBeInTheDocument();
    expect(
      await screen.findByText("No remembered answers yet"),
    ).toBeInTheDocument();
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
  });

  it("editing a bullet PUTs the full profile built from the approved one, keeping ids", async () => {
    api({});
    const edited = profileOut();
    edited.data.experience[0].bullets[0].text = "Reworded";
    apiMock.PUT.mockResolvedValue(ok(edited));
    renderWithClient(<ProfileView />);
    await userEvent.click(
      await screen.findByRole("button", { name: /^Edit:/ }),
    );
    const box = screen.getByLabelText(/Edit achievement/);
    await userEvent.clear(box);
    await userEvent.type(box, "Reworded");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
      await screen.findByRole("region", { name: "Unapproved changes" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Unapproved").length).toBe(1);
    const [path, init] = apiMock.PUT.mock.calls[0];
    expect(path).toBe("/profile/draft");
    expect(init.body.experience[0].bullets[0]).toEqual({
      id: "b1",
      text: "Reworded",
    });
    expect(init.body.contact.email).toBe("asha@example.com");
  });

  it("keeps the text and shows the server's 422 message when saving fails", async () => {
    api({});
    apiMock.PUT.mockResolvedValue(
      fail(422, {
        code: "validation_error",
        message: "x",
        details: [
          {
            loc: ["body", "experience", 0, "bullets", 0, "text"],
            msg: "Too long",
            type: "t",
          },
        ],
      }),
    );
    renderWithClient(<ProfileView />);
    await userEvent.click(
      await screen.findByRole("button", { name: /^Edit:/ }),
    );
    await userEvent.type(screen.getByLabelText(/Edit achievement/), "!");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Too long")).toBeInTheDocument();
    expect(screen.getByLabelText(/Edit achievement/)).toHaveValue(
      "Cut p95 latency by 40% using React!",
    );
  });

  it("adds an achievement (no id sent; the API assigns one)", async () => {
    api({});
    apiMock.PUT.mockResolvedValue(ok(profileOut()));
    renderWithClient(<ProfileView />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Add achievement" }),
    );
    await userEvent.type(
      screen.getByLabelText(/New achievement/),
      "Led a migration",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(apiMock.PUT).toHaveBeenCalled());
    expect(apiMock.PUT.mock.calls[0][1].body.experience[0].bullets[1]).toEqual({
      text: "Led a migration",
    });
  });

  it("shows the unapproved banner for a draft, marks changed bullets and approves it (no discard)", async () => {
    const draft = profileOut();
    draft.data.experience[0].bullets[0].text = "Changed in draft";
    api({ draft });
    apiMock.POST.mockResolvedValue(ok(approved()));
    renderWithClient(<ProfileView />);
    const banner = await screen.findByRole("region", {
      name: "Unapproved changes",
    });
    expect(screen.getByText("Unapproved")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /discard/i }),
    ).not.toBeInTheDocument();
    await userEvent.click(
      within(banner).getByRole("button", { name: "Approve changes" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("region", { name: "Unapproved changes" }),
      ).not.toBeInTheDocument(),
    );
    expect(apiMock.POST.mock.calls[0][0]).toBe("/profile/approve");
  });

  it("shows an empty state when nothing exists, and an error state with retry on failure", async () => {
    api({ approved: null });
    const { unmount } = renderWithClient(<ProfileView />);
    expect(
      await screen.findByText("Your profile is empty"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Upload a resume" }),
    ).toHaveAttribute("href", "/onboarding/upload");
    unmount();
    apiMock.GET.mockResolvedValue(
      fail(500, { code: "server_error", message: "Down" }),
    );
    renderWithClient(<ProfileView />);
    expect(
      await screen.findByText("Couldn't load your profile"),
    ).toBeInTheDocument();
  });

  it("lists remembered answers from /screening-answers", async () => {
    api({
      answers: [
        {
          id: "a1",
          question: "Notice period?",
          answer: "30 days",
          field_type: "text",
          source: "user",
          updated_at: "x",
        },
      ],
    });
    renderWithClient(<ProfileView />);
    expect(await screen.findByText("Notice period?")).toBeInTheDocument();
    expect(screen.getByText("30 days")).toBeInTheDocument();
  });
});
