import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/errors";
import { copyFor } from "./error-copy";

const e = (code: string, status = 409) =>
  new ApiError({ code, message: "server text", status });

describe("copyFor", () => {
  it("prefers the endpoint's mapped copy for a documented code", () => {
    expect(copyFor(e("invalid_state"), { invalid_state: "Reload." })).toBe(
      "Reload.",
    );
  });
  it("falls back to the server message, then to a generic one", () => {
    expect(copyFor(e("something_else"))).toBe("server text");
    expect(copyFor(new Error("boom"))).toMatch(/something went wrong/i);
  });
  it("has default copy for 429 and 422", () => {
    expect(copyFor(e("rate_limited", 429))).toMatch(/too many/i);
    expect(copyFor(e("validation_error", 422))).toMatch(/check/i);
  });
});
