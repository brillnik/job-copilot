import type { StatusTone } from "@/components/ui/chip";
import { humanize } from "@/features/common/format";
import type { components } from "@/lib/api/schema";

export type ApplicationStatus =
  components["schemas"]["ApplicationOut"]["status"];

export const STATUSES: readonly ApplicationStatus[] = [
  "queued",
  "running",
  "waiting_for_user",
  "submitted",
  "skipped",
  "failed",
  "cancelled",
];

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  queued: "Queued",
  running: "Running",
  waiting_for_user: "Needs your answer",
  submitted: "Submitted",
  skipped: "Skipped",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const STATUS_TONE: Record<ApplicationStatus, StatusTone> = {
  queued: "neutral",
  running: "accent",
  waiting_for_user: "warn",
  submitted: "ok",
  skipped: "warn",
  failed: "bad",
  cancelled: "neutral",
};

export const ACTIVE: readonly ApplicationStatus[] = [
  "queued",
  "running",
  "waiting_for_user",
];

export function statusLabel(s: string): string {
  return STATUS_LABEL[s as ApplicationStatus] ?? humanize(s);
}

const REASONS: Record<string, string> = {
  kill_switch: "Applying is switched off right now.",
  ats_disabled: "Applying on this kind of application form is switched off.",
  site_not_opted_in: "You haven't opted in to this site in Autopilot settings.",
  site_paused:
    "This site is paused after it blocked us. Resume it in Autopilot settings.",
  user_cancelled: "You cancelled it.",
  required_field_no_value: "A required field had no saved answer.",
  captcha: "The site showed a CAPTCHA, which we never solve.",
  login: "The site asked for a login, which we never do for you.",
  verification: "The site asked for verification.",
  bot_check: "The site ran a bot check.",
  blocked: "The site blocked the application.",
  draft_flagged:
    "The tailored resume was flagged, so it needs your review first.",
  below_min_score: "The match score was below your minimum.",
  daily_cap: "Your daily apply cap was reached.",
};

/** Friendly text for a backend skip/needs-a-person reason code (unknown codes are humanised). */
export function reasonText(code: string): string {
  return REASONS[code] ?? humanize(code);
}

/** Documented 409/422 codes for POST /runs/{id}/apply and the application actions. */
export const APPLY_ERRORS: Record<string, string> = {
  run_not_approved:
    "Approve this resume in the review queue first, then apply.",
  kill_switch: "Applying is switched off right now. Try again later.",
  ats_disabled:
    "Automatic applying isn't available for this kind of form. Use the direct link instead.",
  site_not_opted_in: "Opt in to this site in Autopilot settings first.",
  site_paused:
    "This site is paused after it blocked us. Resume it in Autopilot settings.",
  invalid_state:
    "This application changed in the meantime. Reload and try again.",
  validation_error:
    "This job can't be applied to automatically (no apply link, or an unsupported site).",
  not_found: "We couldn't find that application or run.",
};
