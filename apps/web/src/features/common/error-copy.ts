import { ApiError, errorMessage } from "@/lib/api/errors";

/** Per-endpoint map from backend error `code` to human copy. */
export type ErrorCopy = Record<string, string>;

/**
 * Human text for a thrown value: a documented code wins, then the server's own
 * message (already user-facing), then a generic network/unknown fallback.
 */
export function copyFor(e: unknown, map: ErrorCopy = {}): string {
  if (e instanceof ApiError) {
    if (map[e.code]) return map[e.code];
    if (e.code === "validation_error")
      return map.validation_error ?? "Check the highlighted values and retry.";
    if (e.code === "rate_limited")
      return map.rate_limited ?? "Too many requests. Wait a moment and retry.";
    if (e.code === "not_found")
      return map.not_found ?? "That item no longer exists.";
    if (e.code === "feature_disabled")
      return "This feature is switched off for your account.";
  }
  return errorMessage(e);
}

export function isCode(e: unknown, ...codes: string[]): boolean {
  return e instanceof ApiError && codes.includes(e.code);
}
