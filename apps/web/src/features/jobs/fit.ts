import type { StatusTone } from "@/components/ui/chip";
import { formatCtc } from "./format";
import type { JobDescription } from "./types";

export type FitChip = { key: string; tone: StatusTone; text: string };

type Prefs = {
  expected_ctc_lpa: number;
  notice_days: number;
  cities: string[];
};

/**
 * Fit between the posting and the user's saved preferences. Uses only what the
 * API returns: the JD has no notice-period field, so notice is shown as the
 * user's own value, never as a verdict.
 */
export function fitChips(jd: JobDescription | null, prefs?: Prefs): FitChip[] {
  if (!jd) return [];
  const chips: FitChip[] = [];
  const ctc = formatCtc(jd.ctc_lpa_min, jd.ctc_lpa_max);
  if (!ctc) {
    chips.push({
      key: "ctc",
      tone: "neutral",
      text: "CTC not stated in the posting",
    });
  } else if (prefs) {
    const top = jd.ctc_lpa_max ?? jd.ctc_lpa_min ?? 0;
    chips.push(
      top >= prefs.expected_ctc_lpa
        ? {
            key: "ctc",
            tone: "ok",
            text: `CTC ${ctc} meets your ${prefs.expected_ctc_lpa} LPA expectation`,
          }
        : {
            key: "ctc",
            tone: "warn",
            text: `CTC ${ctc} is below your ${prefs.expected_ctc_lpa} LPA expectation`,
          },
    );
  } else {
    chips.push({ key: "ctc", tone: "neutral", text: `CTC ${ctc}` });
  }

  if (jd.work_mode === "remote") {
    chips.push({ key: "loc", tone: "ok", text: "Remote" });
  } else if (jd.location && prefs) {
    const loc = jd.location.toLowerCase();
    const hit = prefs.cities.find((c) => {
      const city = c.toLowerCase();
      return city && (loc.includes(city) || city.includes(loc));
    });
    chips.push(
      hit
        ? {
            key: "loc",
            tone: "ok",
            text: `${jd.location} is one of your cities`,
          }
        : {
            key: "loc",
            tone: "warn",
            text: `${jd.location} is outside your cities`,
          },
    );
  } else if (jd.location) {
    chips.push({ key: "loc", tone: "neutral", text: jd.location });
  }

  if (prefs) {
    chips.push({
      key: "notice",
      tone: "neutral",
      text: `Your notice period: ${prefs.notice_days} days (the posting doesn't state one)`,
    });
  }
  return chips;
}
