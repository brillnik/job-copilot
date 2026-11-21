import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { beforeEach, describe, expect, it, vi } from "vitest";

const GET = vi.fn();
const PATCH = vi.fn();
vi.mock("@/lib/api/browser", () => ({
  api: {
    GET: (...a: unknown[]) => GET(...a),
    PATCH: (...a: unknown[]) => PATCH(...a),
    DELETE: vi.fn(),
  },
}));

import { ToastProvider } from "@/components/ui/toast";
import { moveInBoard, previewIsComplete } from "./api";
import { boardFixture, cardFixture } from "./fixtures";
import { TrackerBoard } from "./tracker-board";

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <TrackerBoard />
      </ToastProvider>
    </QueryClientProvider>,
  );
}
const ok = (data: unknown) => ({ data, response: new Response() });

beforeEach(() => {
  GET.mockReset();
  PATCH.mockReset();
  GET.mockResolvedValue(ok(boardFixture()));
});

describe("moveInBoard", () => {
  it("moves a card to an index and keeps counts in step", () => {
    const next = moveInBoard(boardFixture(), "c1", "approved", 0);
    expect(next.columns.approved.map((c) => c.id)).toEqual(["c1", "c0"]);
    expect(next.columns.applied).toEqual([]);
    expect(next.stats.counts).toMatchObject({ approved: 2, applied: 0 });
  });
});

describe("previewIsComplete", () => {
  it("treats a truncated preview as incomplete", () => {
    expect(previewIsComplete("short note")).toBe(true);
    expect(previewIsComplete(null)).toBe(true);
    expect(previewIsComplete("x".repeat(119) + "…")).toBe(false);
  });
});

describe("TrackerBoard", () => {
  it("renders stats and columns without axe violations", async () => {
    const { container } = wrap();
    expect(await screen.findByText("Applied this week")).toBeVisible();
    expect(screen.getByText("25%")).toBeVisible();
    expect(screen.getByText("78")).toBeVisible();
    expect(screen.getByRole("heading", { name: /Interview/ })).toBeVisible();
    expect(
      await axe(container, { iframes: false } as never),
    ).toHaveNoViolations();
  });

  it("moves with the keyboard optimistically and sends If-Match + column", async () => {
    let resolve: (v: unknown) => void = () => {};
    PATCH.mockReturnValue(new Promise((r) => (resolve = r)));
    wrap();
    const user = userEvent.setup();
    const card = await screen.findByRole("button", {
      name: /Frontend Engineer, Acme/,
    });
    card.focus();
    await user.keyboard(" {ArrowRight} ");
    const response = screen.getByRole("region", { name: "Application board" });
    // Optimistic: already in the Response column before the server answered.
    await waitFor(() =>
      expect(
        within(
          within(response).getByRole("list", { name: "Response cards" }),
        ).getByText("Frontend Engineer"),
      ).toBeVisible(),
    );
    expect(PATCH.mock.calls[0][1]).toMatchObject({
      params: { path: { card_id: "c1" }, header: { "if-match": '"2"' } },
      body: { column: "response" },
    });
    resolve(
      ok({
        ...cardFixture({ column: "response", rev: 3 }),
        notes: "Spoke to recruiter",
        position: 1,
        history: [],
      }),
    );
  });

  it("rolls back and explains on a 409 stale write", async () => {
    PATCH.mockResolvedValue({
      error: { code: "stale_write", message: "stale" },
      response: new Response(null, { status: 409 }),
    });
    wrap();
    const user = userEvent.setup();
    const card = await screen.findByRole("button", {
      name: /Frontend Engineer, Acme/,
    });
    card.focus();
    await user.keyboard(" {ArrowRight} ");
    expect(
      (await screen.findAllByText(/changed somewhere else/)).length,
    ).toBeGreaterThan(0);
    const applied = within(screen.getByRole("list", { name: "Applied cards" }));
    expect(applied.getByText("Frontend Engineer")).toBeVisible();
    expect(
      within(screen.getByRole("list", { name: "Response cards" })).queryByText(
        "Frontend Engineer",
      ),
    ).toBeNull();
  });

  it("edits a short note from the details dialog and sends it with If-Match", async () => {
    PATCH.mockResolvedValue(
      ok({
        ...cardFixture({
          rev: 3,
          notes_preview: "Spoke to recruiter. Follow up Monday.",
        }),
        notes: "Spoke to recruiter. Follow up Monday.",
        position: 1,
        history: [],
      }),
    );
    wrap();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", {
        name: /Details for Frontend Engineer/,
      }),
    );
    const notes = await screen.findByLabelText("Notes");
    expect(notes).toHaveValue("Spoke to recruiter");
    await user.type(notes, ". Follow up Monday.");
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(PATCH).toHaveBeenCalled());
    expect(PATCH.mock.calls[0][1]).toMatchObject({
      params: { header: { "if-match": '"2"' } },
      body: { notes: "Spoke to recruiter. Follow up Monday." },
    });
  });

  it("does not pretend to edit a note that is longer than the preview", async () => {
    const b = boardFixture();
    b.columns.applied[0].notes_preview = "x".repeat(119) + "…";
    GET.mockResolvedValue(ok(b));
    wrap();
    await userEvent.click(
      await screen.findByRole("button", {
        name: /Details for Frontend Engineer/,
      }),
    );
    expect(
      await screen.findByText(/can't be edited without replacing it/),
    ).toBeVisible();
    expect(screen.queryByLabelText("Notes")).toBeNull();
    await userEvent.click(
      screen.getByRole("button", { name: "Replace the note" }),
    );
    expect(screen.getByLabelText(/New note/)).toHaveValue("");
  });

  it("shows an empty state and a retryable error", async () => {
    GET.mockResolvedValueOnce({
      error: { code: "server_error", message: "boom" },
      response: new Response(null, { status: 500 }),
    });
    wrap();
    expect(
      await screen.findByRole(
        "button",
        { name: "Try again" },
        { timeout: 4000 },
      ),
    ).toBeVisible();
  });
});
