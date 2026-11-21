// PLACEHOLDER POLICY TEXT. The API serves only the policy *version* (GET /autopilot
// -> policy_version), not the text. A human (product/legal) must review and replace
// these constants; the UI always sends the version the API reports, so replacing the
// text here is safe only together with bumping AUTOPILOT_POLICY_VERSION on the server.

export const AUTOPILOT_ACK_TEXT =
  "I understand that Autopilot applies to jobs on my behalf using my approved resume and saved answers. " +
  "It never solves CAPTCHAs, never signs in for me and never guesses answers: when a site blocks it or a required answer is missing, " +
  "it skips the job and lists it in my daily digest with a direct link so I can apply myself.";

export const AUTOPILOT_WHAT_IT_DOES: readonly string[] = [
  "Applies to jobs that score at or above your minimum, up to your daily cap.",
  "Only uses resumes you have already approved and answers you have saved.",
  "Never solves CAPTCHAs or logs in for you. If a site blocks it, the job is skipped.",
  "Sends you a daily digest of what was submitted, skipped and needs a person.",
];

export type SiteKey = "wellfound" | "naukri" | "hiring_cafe";

export const SITE_POLICY: Record<
  SiteKey,
  { label: string; risk: string; ack: string }
> = {
  wellfound: {
    label: "Wellfound",
    risk: "Wellfound applications run through your own browser extension while you are signed in to Wellfound. Automated activity may go against the site's terms and could lead to warnings or restrictions on your account.",
    ack: "I understand the risk and want Autopilot to apply on Wellfound through my browser extension.",
  },
  naukri: {
    label: "Naukri",
    risk: "Naukri applications run through your own browser extension while you are signed in to Naukri. Automated activity may go against the site's terms and could lead to warnings or restrictions on your account.",
    ack: "I understand the risk and want Autopilot to apply on Naukri through my browser extension.",
  },
  hiring_cafe: {
    label: "Hiring Cafe",
    risk: "Hiring Cafe applications run through your own browser extension. Automated activity may go against the site's terms and could lead to warnings or restrictions on your account.",
    ack: "I understand the risk and want Autopilot to apply on Hiring Cafe through my browser extension.",
  },
};

export const SITE_KEYS = Object.keys(SITE_POLICY) as SiteKey[];
