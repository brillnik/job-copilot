import { ApiError } from "@/lib/api/errors";

export type TailorProblem = {
  code: string;
  /** Exact human copy shown to the user. */
  message: string;
  /** Where the user can fix it, when there is somewhere. */
  fix?: { href: string; label: string };
  redFlags?: string[];
  runId?: string;
};

function detail<T>(e: ApiError, key: string): T | undefined {
  const d = e.details;
  if (d && !Array.isArray(d)) return (d as Record<string, unknown>)[key] as T;
  return undefined;
}

/** Human copy for each documented 409/429 code of POST /jobs/{id}/tailor. */
export function tailorProblem(
  e: unknown,
  opts: { resetsAt?: string } = {},
): TailorProblem {
  if (!(e instanceof ApiError)) {
    return {
      code: "unknown",
      message: "Something went wrong. Check your connection and try again.",
    };
  }
  switch (e.code) {
    case "jd_not_ready":
      return {
        code: e.code,
        message:
          "This job's description isn't ready yet. Wait for it to finish processing, or paste the posting text.",
      };
    case "red_flags":
      return {
        code: e.code,
        message:
          "This posting has red flags. Review them and confirm to continue.",
        redFlags: detail<string[]>(e, "red_flags") ?? [],
      };
    case "no_profile":
      return {
        code: e.code,
        message: "Approve your profile before tailoring a resume.",
        fix: { href: "/profile", label: "Go to your profile" },
      };
    case "profile_indexing":
      return {
        code: e.code,
        message: "Your profile is still being indexed. Try again in a minute.",
      };
    case "run_in_progress":
      return {
        code: e.code,
        message: "A tailoring run is already in progress for this job.",
        runId: detail<string>(e, "run_id"),
      };
    case "invalid_state":
      return {
        code: e.code,
        message:
          "This job can't be tailored in its current state. It may be archived.",
      };
    case "daily_cap": {
      const used = detail<number>(e, "used");
      const cap = detail<number>(e, "cap");
      return {
        code: e.code,
        message:
          used !== undefined && cap !== undefined
            ? dailyCapCopy(used, cap, opts.resetsAt)
            : "You've reached today's tailoring limit.",
      };
    }
    default:
      return { code: e.code, message: e.message };
  }
}

export function dailyCapCopy(used: number, cap: number, resetsAt?: string) {
  const when = resetsAt
    ? ` The limit resets at ${new Date(resetsAt).toLocaleTimeString([], {
        hour: "numeric",
        minute: "2-digit",
      })}.`
    : "";
  return `You've used ${used} of ${cap} tailoring runs today.${when}`;
}
