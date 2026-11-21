import { beforeEach, describe, expect, it, vi } from "vitest";

const GET = vi.fn();
const PUT = vi.fn();
vi.mock("@/lib/api/browser", () => ({
  api: {
    GET: (...a: unknown[]) => GET(...a),
    PUT: (...a: unknown[]) => PUT(...a),
  },
}));

import { updatePreferences } from "./use-settings";

const prefs = {
  target_roles: ["SWE"],
  cities: ["Pune"],
  current_ctc_lpa: 10,
  expected_ctc_lpa: 15,
  notice_days: 30,
  default_length: "auto",
  template: "classic",
  daily_cap: 5,
  coverage_target: 80,
  theme: "system",
};
const settingsResponse = (rev: number) => ({
  data: {
    preferences: prefs,
    configured: true,
    rev,
    runs_used_today: 0,
    daily_cap: 5,
    cap_resets_at: "x",
  },
  response: new Response(null, { headers: { etag: `"${rev}"` } }),
});

describe("updatePreferences (read-modify-write with If-Match)", () => {
  beforeEach(() => {
    GET.mockReset();
    PUT.mockReset();
  });

  it("sends the full preferences with only the patch changed and the current ETag", async () => {
    GET.mockResolvedValueOnce(settingsResponse(3));
    PUT.mockResolvedValueOnce({ data: { rev: 4 }, response: new Response() });
    await updatePreferences({ theme: "dark" });
    expect(PUT).toHaveBeenCalledWith("/settings", {
      body: { ...prefs, theme: "dark" },
      params: { header: { "if-match": '"3"' } },
    });
  });

  it("retries once against a fresh read on a stale write", async () => {
    GET.mockResolvedValueOnce(settingsResponse(3)).mockResolvedValueOnce(
      settingsResponse(4),
    );
    PUT.mockResolvedValueOnce({
      error: { code: "stale_write", message: "stale" },
      response: new Response(null, { status: 409 }),
    }).mockResolvedValueOnce({ data: { rev: 5 }, response: new Response() });
    await updatePreferences({ theme: "light" });
    expect(PUT).toHaveBeenCalledTimes(2);
    expect(PUT.mock.calls[1][1].params.header["if-match"]).toBe('"4"');
  });

  it("throws a normalised ApiError when the second attempt also fails", async () => {
    GET.mockResolvedValue(settingsResponse(3));
    PUT.mockResolvedValue({
      error: { code: "stale_write", message: "stale" },
      response: new Response(null, { status: 409 }),
    });
    await expect(updatePreferences({ theme: "dark" })).rejects.toMatchObject({
      code: "stale_write",
      status: 409,
    });
  });
});
