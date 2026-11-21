import { describe, expect, it } from "vitest";
import { ApiError, errorMessage, toApiError } from "./errors";

describe("toApiError", () => {
  it("keeps the backend {code,message,details} shape", () => {
    const e = toApiError(
      { code: "invalid", message: "Bad", details: { f: 1 } },
      422,
    );
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({
      code: "invalid",
      message: "Bad",
      status: 422,
      details: { f: 1 },
    });
  });
  it("maps the proxy's {detail} 401 to unauthenticated", () => {
    const e = toApiError({ detail: "Not authenticated" }, 401);
    expect(e.code).toBe("unauthenticated");
    expect(e.isUnauthenticated).toBe(true);
  });
  it("gives a friendly message for 5xx and unknown errors", () => {
    expect(toApiError(undefined, 502).code).toBe("server_error");
    expect(errorMessage(new TypeError("x"))).toMatch(/something went wrong/i);
  });
});
