import { ApiError } from "./errors";

export type FieldErrors = Record<string, string>;

type Detail = { loc?: unknown; msg?: unknown };

const clean = (msg: string) => msg.replace(/^Value error,\s*/i, "");

/**
 * Map a 422 `{code:"validation_error", details:[{loc,msg,type}]}` onto form
 * fields. `loc` is `["body", "experience", 0, "company"]`, which becomes the
 * dotted path `experience.0.company`. Errors with no field (empty path) are
 * returned under the "" key. Messages only; submitted values are never read.
 */
export function fieldErrors(e: unknown): FieldErrors {
  if (!(e instanceof ApiError) || e.status !== 422) return {};
  const out: FieldErrors = {};
  if (!Array.isArray(e.details)) return out;
  for (const d of e.details as Detail[]) {
    if (!d || !Array.isArray(d.loc) || typeof d.msg !== "string") continue;
    const loc = d.loc as Array<string | number>;
    const path = (loc[0] === "body" ? loc.slice(1) : loc).join(".");
    out[path] ??= clean(d.msg);
  }
  return out;
}
