const dateTime = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
});
const date = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" });

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : dateTime.format(d);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : date.format(d);
}

/** "kill_switch" -> "Kill switch" for backend reason codes without bespoke copy. */
export function humanize(code: string): string {
  const s = code.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const SITE_LABEL: Record<string, string> = {
  wellfound: "Wellfound",
  naukri: "Naukri",
  hiring_cafe: "Hiring Cafe",
};

export function siteLabel(site: string): string {
  return SITE_LABEL[site] ?? humanize(site);
}
