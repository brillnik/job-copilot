import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getEvents: vi.fn() }));
vi.mock("./api", () => api);

import { resetJobEventsCursor, useJobEvents } from "./use-job-events";

function setup(onUpdate?: (t: string[]) => void) {
  const client = new QueryClient();
  const spy = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = renderHook(() => useJobEvents(onUpdate), { wrapper });
  return { spy, ...view };
}
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));
const ev = (id: number, type: string) => ({
  id,
  type,
  payload: {},
  created_at: "x",
});

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  resetJobEventsCursor();
  Object.defineProperty(document, "hidden", {
    value: false,
    configurable: true,
  });
});
afterEach(() => vi.useRealTimers());

describe("useJobEvents (polling GET /events)", () => {
  it("polls with last_id and invalidates jobs on events", async () => {
    api.getEvents
      .mockResolvedValueOnce({ events: [ev(4, "job_ready")], last_id: 4 })
      .mockResolvedValue({ events: [], last_id: 4 });
    const onUpdate = vi.fn();
    const { spy } = setup(onUpdate);
    await tick(0);
    expect(api.getEvents).toHaveBeenNthCalledWith(1, 0);
    expect(spy).toHaveBeenCalledWith({ queryKey: ["jobs"] });
    expect(onUpdate).toHaveBeenCalledWith(["job_ready"]);
    await tick(3000);
    expect(api.getEvents).toHaveBeenLastCalledWith(4);
  });

  it("also refreshes runs and settings on run_* events", async () => {
    api.getEvents.mockResolvedValueOnce({
      events: [ev(1, "run_status")],
      last_id: 1,
    });
    api.getEvents.mockResolvedValue({ events: [], last_id: 1 });
    const { spy } = setup();
    await tick(0);
    const keys = spy.mock.calls.map((c) =>
      JSON.stringify((c[0] as { queryKey: unknown }).queryKey),
    );
    expect(keys).toEqual(
      expect.arrayContaining(['["jobs"]', '["runs"]', '["settings"]']),
    );
  });

  it("backs off when idle and stops on unmount", async () => {
    api.getEvents.mockResolvedValue({ events: [], last_id: 0 });
    const { unmount } = setup();
    await tick(0); // 1st poll, then 4.5 s
    await tick(4500); // 2nd poll, then 6.75 s
    await tick(4500);
    expect(api.getEvents).toHaveBeenCalledTimes(2);
    await tick(2250);
    expect(api.getEvents).toHaveBeenCalledTimes(3);
    unmount();
    await tick(60_000);
    expect(api.getEvents).toHaveBeenCalledTimes(3);
  });

  it("does not poll while the tab is hidden and resumes when visible", async () => {
    Object.defineProperty(document, "hidden", {
      value: true,
      configurable: true,
    });
    api.getEvents.mockResolvedValue({ events: [], last_id: 0 });
    setup();
    await tick(0);
    await tick(20_000);
    expect(api.getEvents).not.toHaveBeenCalled();
    Object.defineProperty(document, "hidden", {
      value: false,
      configurable: true,
    });
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(api.getEvents).toHaveBeenCalledTimes(1);
  });

  it("survives a failed poll", async () => {
    api.getEvents.mockRejectedValueOnce(new Error("offline"));
    api.getEvents.mockResolvedValue({
      events: [ev(2, "job_failed")],
      last_id: 2,
    });
    const onUpdate = vi.fn();
    setup(onUpdate);
    await tick(0);
    await tick(4500);
    expect(onUpdate).toHaveBeenCalledWith(["job_failed"]);
  });
});
