import { describe, expect, it } from "vitest";
import { ApiError } from "./errors";
import { fieldErrors } from "./field-errors";

const err = (status: number, details: unknown) =>
  new ApiError({
    code: "validation_error",
    message: "Request validation failed",
    status,
    details: details as never,
  });

describe("fieldErrors", () => {
  it("maps loc to dotted form paths and strips the body prefix", () => {
    expect(
      fieldErrors(
        err(422, [
          {
            loc: ["body", "experience", 0, "company"],
            msg: "Field required",
            type: "missing",
          },
          {
            loc: ["body", "cities"],
            msg: "Value error, unknown city; allowed: Pune",
            type: "value_error",
          },
        ]),
      ),
    ).toEqual({
      "experience.0.company": "Field required",
      cities: "unknown city; allowed: Pune",
    });
  });
  it("keeps the first message per field and ignores non-422 / odd shapes", () => {
    expect(
      fieldErrors(
        err(422, [
          { loc: ["body", "a"], msg: "one", type: "x" },
          { loc: ["body", "a"], msg: "two", type: "x" },
          { nope: true },
        ]),
      ),
    ).toEqual({ a: "one" });
    expect(fieldErrors(err(409, []))).toEqual({});
    expect(fieldErrors(new Error("x"))).toEqual({});
    expect(fieldErrors(err(422, { a: 1 }))).toEqual({});
  });
});
