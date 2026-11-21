import { z } from "zod";
import type { Preferences } from "@/hooks/use-settings";

/**
 * The backend validates cities against `settings.allowed_cities`, which is NOT in the
 * OpenAPI schema (a plain string array), so this list mirrors the backend defaults.
 */
export const CITIES = [
  "Remote",
  "Bengaluru",
  "Hyderabad",
  "Pune",
  "Mumbai",
  "Delhi NCR",
  "Chennai",
  "Kolkata",
  "Ahmedabad",
  "Kochi",
  "Jaipur",
  "Chandigarh",
] as const;

/** Server ceiling for `daily_cap` (settings.daily_cap_max); not exposed by the API. */
export const DAILY_CAP_MAX = 50;

export const LENGTHS = ["auto", "1", "2", "3"] as const;
export const COVERAGE_TARGETS = ["0.5", "0.6", "0.7", "0.8"] as const;

const num = (label: string) => ({ error: `Enter ${label} as a number` });

export const preferencesSchema = z.object({
  target_roles: z
    .array(
      z
        .string()
        .trim()
        .min(1)
        .max(80, "Each role can be at most 80 characters"),
    )
    .min(1, "Add at least one target role")
    .max(10, "At most 10 roles"),
  cities: z.array(z.enum(CITIES)).max(30),
  current_ctc_lpa: z
    .number(num("your current CTC"))
    .min(0, "Can't be negative")
    .max(500, "At most 500 LPA"),
  expected_ctc_lpa: z
    .number(num("your expected CTC"))
    .min(0, "Can't be negative")
    .max(500, "At most 500 LPA"),
  notice_days: z
    .number(num("your notice period"))
    .int("Whole days only")
    .min(0, "Can't be negative")
    .max(180, "At most 180 days"),
  default_length: z.enum(LENGTHS),
  template: z.enum(["classic", "compact"]),
  daily_cap: z
    .number(num("a daily limit"))
    .int("Whole numbers only")
    .min(1, "At least 1")
    .max(DAILY_CAP_MAX, `At most ${DAILY_CAP_MAX}`),
  coverage_target: z.enum(COVERAGE_TARGETS),
});
export type FormValues = z.infer<typeof preferencesSchema>;

export function toFormValues(p: Preferences): FormValues {
  const known = new Set<string>(CITIES);
  return {
    target_roles: p.target_roles,
    cities: p.cities.filter((c): c is (typeof CITIES)[number] => known.has(c)),
    current_ctc_lpa: p.current_ctc_lpa,
    expected_ctc_lpa: p.expected_ctc_lpa,
    notice_days: p.notice_days,
    default_length: String(p.default_length) as FormValues["default_length"],
    template: p.template,
    daily_cap: p.daily_cap,
    coverage_target: (COVERAGE_TARGETS.includes(
      String(p.coverage_target) as never,
    )
      ? String(p.coverage_target)
      : "0.7") as FormValues["coverage_target"],
  };
}

/** Form values + the account theme (managed by the Appearance card) -> API body. */
export function toPreferences(
  v: FormValues,
  theme: Preferences["theme"],
): Preferences {
  return {
    ...v,
    default_length:
      v.default_length === "auto"
        ? "auto"
        : (Number(v.default_length) as 1 | 2 | 3),
    coverage_target: Number(v.coverage_target),
    theme,
  };
}
