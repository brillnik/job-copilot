import type { Preferences } from "@/hooks/use-settings";
import { ALLOWED_CITIES } from "./constants";

export type PrefValues = {
  roles: string[];
  cities: string[];
  currentCtc: string;
  expectedCtc: string;
  noticeDays: string;
  defaultLength: "auto" | "1" | "2" | "3";
  template: Preferences["template"];
};

export type PrefErrors = Partial<Record<keyof PrefValues, string>>;

export function toPrefValues(p: Preferences): PrefValues {
  return {
    roles: p.target_roles,
    cities: p.cities,
    currentCtc: String(p.current_ctc_lpa),
    expectedCtc: String(p.expected_ctc_lpa),
    noticeDays: String(p.notice_days),
    defaultLength: String(p.default_length) as PrefValues["defaultLength"],
    template: p.template,
  };
}

const num = (s: string) => (s.trim() === "" ? NaN : Number(s));

export function validatePrefs(v: PrefValues): PrefErrors {
  const e: PrefErrors = {};
  if (v.roles.length < 1) e.roles = "Add at least one role you're targeting";
  if (v.roles.length > 10) e.roles = "At most 10 roles";
  for (const k of ["currentCtc", "expectedCtc"] as const) {
    const n = num(v[k]);
    if (!Number.isFinite(n) || n < 0 || n > 500)
      e[k] = "Enter a number between 0 and 500";
  }
  const d = num(v.noticeDays);
  if (!Number.isInteger(d) || d < 0 || d > 180)
    e.noticeDays = "Enter whole days, 0 to 180";
  return e;
}

/** Full-replace body: only the fields on this screen change; the rest is kept as read. */
export function toPreferences(v: PrefValues): Partial<Preferences> {
  return {
    target_roles: v.roles,
    cities: v.cities,
    current_ctc_lpa: Number(v.currentCtc),
    expected_ctc_lpa: Number(v.expectedCtc),
    notice_days: Number(v.noticeDays),
    default_length: v.defaultLength === "auto" ? "auto" : (Number(v.defaultLength) as 1 | 2 | 3),
    template: v.template,
  };
}

/** Server field names to this form's keys. */
export const PREF_FIELD: Record<string, keyof PrefValues> = {
  target_roles: "roles",
  cities: "cities",
  current_ctc_lpa: "currentCtc",
  expected_ctc_lpa: "expectedCtc",
  notice_days: "noticeDays",
  default_length: "defaultLength",
  template: "template",
};

/** The allowed list, plus anything already saved that is not on it (so it can be unticked). */
export function cityOptions(selected: string[]): string[] {
  return [...ALLOWED_CITIES, ...selected.filter((c) => !(ALLOWED_CITIES as readonly string[]).includes(c))];
}
