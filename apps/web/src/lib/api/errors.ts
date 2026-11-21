import type { components } from "./schema";

export type ApiErrorBody = components["schemas"]["ErrorBody"];

// Backend errors are {code, message, details?}. The Next proxy answers 401
// with {detail}, and network failures have no response at all; both are
// normalised into the same shape so UI code only ever handles ApiError.
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details?: ApiErrorBody["details"];

  constructor(init: {
    code: string;
    message: string;
    status: number;
    details?: ApiErrorBody["details"];
  }) {
    super(init.message);
    this.name = "ApiError";
    this.code = init.code;
    this.status = init.status;
    this.details = init.details;
  }

  get isUnauthenticated() {
    return this.status === 401;
  }
  get isStaleWrite() {
    return (
      this.status === 409 || this.status === 412 || this.code === "stale_write"
    );
  }
}

export function isApiError(e: unknown): e is ApiError {
  return e instanceof ApiError;
}

function isErrorBody(x: unknown): x is ApiErrorBody {
  return (
    typeof x === "object" &&
    x !== null &&
    typeof (x as ApiErrorBody).code === "string" &&
    typeof (x as ApiErrorBody).message === "string"
  );
}

export function toApiError(body: unknown, status: number): ApiError {
  if (isErrorBody(body)) {
    return new ApiError({
      code: body.code,
      message: body.message,
      status,
      details: body.details,
    });
  }
  if (status === 401) {
    return new ApiError({
      code: "unauthenticated",
      message: "Your session has expired. Sign in again.",
      status,
    });
  }
  return new ApiError({
    code: status >= 500 ? "server_error" : "request_failed",
    message:
      status >= 500
        ? "Something went wrong on our side. Try again."
        : "The request could not be completed.",
    status,
  });
}

/** Friendly text for any thrown value (never includes request data). */
export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Something went wrong. Check your connection and try again.";
}
