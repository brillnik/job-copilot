import type { ProfileData } from "@/hooks/use-profile";

// ProfileData <-> form values. The form works with plain strings (no nulls);
// converting back turns "" into null. Entry and bullet ids are kept so that
// citations from generated resumes keep pointing at the same bullet; new
// entries simply have no id and the API assigns one.

export type BulletValue = { id?: string; text: string };
export type FormValues = {
  contact: {
    name: string;
    email: string;
    phone: string;
    location: string;
    linksText: string;
  };
  summary: string;
  experience: Array<{
    id?: string;
    company: string;
    title: string;
    location: string;
    start: string;
    end: string;
    bullets: BulletValue[];
  }>;
  projects: Array<{
    id?: string;
    name: string;
    description: string;
    bullets: BulletValue[];
  }>;
  education: Array<{
    id?: string;
    institution: string;
    degree: string;
    start: string;
    end: string;
  }>;
  skillsText: string;
};

/** A valid, empty profile (what `PUT /profile/draft` needs to start from scratch). */
export const EMPTY_PROFILE: ProfileData = {
  contact: { links: [] },
  experience: [],
  projects: [],
  education: [],
  skills: [],
};

const s = (v: string | null | undefined) => v ?? "";
const n = (v: string) => (v.trim() === "" ? null : v.trim());

export function toFormValues(d: ProfileData): FormValues {
  return {
    contact: {
      name: s(d.contact?.name),
      email: s(d.contact?.email),
      phone: s(d.contact?.phone),
      location: s(d.contact?.location),
      linksText: (d.contact?.links ?? []).join("\n"),
    },
    summary: s(d.summary),
    experience: (d.experience ?? []).map((e) => ({
      id: e.id,
      company: e.company,
      title: s(e.title),
      location: s(e.location),
      start: s(e.start),
      end: s(e.end),
      bullets: (e.bullets ?? []).map((b) => ({ id: b.id, text: b.text })),
    })),
    projects: (d.projects ?? []).map((p) => ({
      id: p.id,
      name: p.name,
      description: s(p.description),
      bullets: (p.bullets ?? []).map((b) => ({ id: b.id, text: b.text })),
    })),
    education: (d.education ?? []).map((e) => ({
      id: e.id,
      institution: e.institution,
      degree: s(e.degree),
      start: s(e.start),
      end: s(e.end),
    })),
    skillsText: (d.skills ?? []).join(", "),
  };
}

const bullets = (list: BulletValue[]) =>
  list.map((b) => ({ ...(b.id ? { id: b.id } : {}), text: b.text.trim() }));

export function splitSkills(text: string): string[] {
  const seen = new Set<string>();
  return text
    .split(/[,\n]/)
    .map((x) => x.trim())
    .filter(
      (x) => x && !seen.has(x.toLowerCase()) && seen.add(x.toLowerCase()),
    );
}

export function toProfileData(v: FormValues): ProfileData {
  return {
    contact: {
      name: n(v.contact.name),
      email: n(v.contact.email),
      phone: n(v.contact.phone),
      location: n(v.contact.location),
      links: v.contact.linksText
        .split("\n")
        .map((x) => x.trim())
        .filter(Boolean),
    },
    summary: n(v.summary),
    experience: v.experience.map((e) => ({
      ...(e.id ? { id: e.id } : {}),
      company: e.company.trim(),
      title: n(e.title),
      location: n(e.location),
      start: n(e.start),
      end: n(e.end),
      bullets: bullets(e.bullets),
    })),
    projects: v.projects.map((p) => ({
      ...(p.id ? { id: p.id } : {}),
      name: p.name.trim(),
      description: n(p.description),
      bullets: bullets(p.bullets),
    })),
    education: v.education.map((e) => ({
      ...(e.id ? { id: e.id } : {}),
      institution: e.institution.trim(),
      degree: n(e.degree),
      start: n(e.start),
      end: n(e.end),
    })),
    skills: splitSkills(v.skillsText),
  };
}

/** Server paths (`contact.links.0`, `skills.2`) to the form's field names. */
export function toFormPath(path: string): string {
  return path
    .replace(/^contact\.links(\.\d+)?$/, "contact.linksText")
    .replace(/^skills(\.\d+)?$/, "skillsText");
}

// --- Review flags ---------------------------------------------------------
// The API returns no per-field confidence, so "needs a second look" can only be
// derived from what is missing or malformed in the draft.

export type ReviewFlag = {
  path: string;
  label: string;
  /** Short reason shown in amber next to the field. */
  reason: string;
  /** Label of the "this is fine as it is" confirmation. */
  confirmLabel: string;
};

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function findFlags(v: FormValues): ReviewFlag[] {
  const flags: ReviewFlag[] = [];
  const add = (
    path: string,
    label: string,
    reason: string,
    confirmLabel: string,
  ) => flags.push({ path, label, reason, confirmLabel });

  if (!v.contact.name.trim())
    add(
      "contact.name",
      "Name",
      "Missing: no name was found.",
      "Leave my name blank",
    );
  if (!v.contact.email.trim())
    add(
      "contact.email",
      "Email",
      "Missing: no email was found.",
      "Leave my email blank",
    );
  else if (!EMAIL.test(v.contact.email.trim()))
    add(
      "contact.email",
      "Email",
      "This doesn't look like an email address.",
      "This email is correct",
    );
  if (!v.skillsText.trim())
    add(
      "skillsText",
      "Skills",
      "Missing: no skills were found.",
      "I have no skills to list",
    );
  if (v.experience.length === 0)
    add(
      "experience",
      "Experience",
      "Missing: no work experience was found.",
      "I have no work experience",
    );
  v.experience.forEach((e, i) => {
    const who = e.company.trim() || `Role ${i + 1}`;
    if (!e.title.trim())
      add(
        `experience.${i}.title`,
        `${who}: job title`,
        "Missing: no job title was found.",
        "Leave the title blank",
      );
    if (!e.start.trim())
      add(
        `experience.${i}.start`,
        `${who}: start date`,
        "Missing: no start date was found.",
        "Leave the start date blank",
      );
    if (!e.end.trim())
      add(
        `experience.${i}.end`,
        `${who}: end date`,
        "Missing: no end date. Fine only if this is your current role.",
        "This is my current role",
      );
    if (e.bullets.length === 0)
      add(
        `experience.${i}.bullets`,
        `${who}: achievements`,
        "Missing: no achievements were found.",
        "Leave this role without achievements",
      );
  });
  return flags;
}

/** Flags that still block "Continue". */
export function unresolvedFlags(flags: ReviewFlag[], confirmed: Set<string>) {
  return flags.filter((f) => !confirmed.has(f.path));
}

// --- Profile page helpers -------------------------------------------------

export type BulletRef = {
  section: "experience" | "projects";
  entryId: string;
  entryLabel: string;
  bullet: { id: string; text: string };
};

export function listBullets(d: ProfileData): BulletRef[] {
  const out: BulletRef[] = [];
  for (const e of d.experience ?? [])
    for (const b of e.bullets ?? [])
      out.push({
        section: "experience",
        entryId: e.id!,
        entryLabel: [e.title, e.company].filter(Boolean).join(" at "),
        bullet: { id: b.id!, text: b.text },
      });
  for (const p of d.projects ?? [])
    for (const b of p.bullets ?? [])
      out.push({
        section: "projects",
        entryId: p.id!,
        entryLabel: p.name,
        bullet: { id: b.id!, text: b.text },
      });
  return out;
}

/** Copy of `d` with one bullet's text replaced; ids are untouched. */
export function replaceBullet(
  d: ProfileData,
  bulletId: string,
  text: string,
): ProfileData {
  const swap = <T extends { bullets?: Array<{ id?: string; text: string }> }>(
    e: T,
  ): T => ({
    ...e,
    bullets: (e.bullets ?? []).map((b) =>
      b.id === bulletId ? { ...b, text } : b,
    ),
  });
  return {
    ...d,
    experience: (d.experience ?? []).map(swap),
    projects: (d.projects ?? []).map(swap),
  };
}

/** Copy of `d` with a new bullet (no id: the API assigns one) appended to an entry. */
export function addBullet(
  d: ProfileData,
  entryId: string,
  text: string,
): ProfileData {
  const add = <
    T extends { id?: string; bullets?: Array<{ id?: string; text: string }> },
  >(
    e: T,
  ): T =>
    e.id === entryId ? { ...e, bullets: [...(e.bullets ?? []), { text }] } : e;
  return {
    ...d,
    experience: (d.experience ?? []).map(add),
    projects: (d.projects ?? []).map(add),
  };
}

/** Ids of bullets in `draft` that are new or reworded compared to `approved`. */
export function unapprovedBulletIds(
  approved: ProfileData | null,
  draft: ProfileData,
): Set<string> {
  const base = new Map(
    approved
      ? listBullets(approved).map((r) => [r.bullet.id, r.bullet.text])
      : [],
  );
  const out = new Set<string>();
  for (const r of listBullets(draft))
    if (base.get(r.bullet.id) !== r.bullet.text) out.add(r.bullet.id);
  return out;
}

const METRIC =
  /(?<![A-Za-z0-9.,])(?:[$₹]\s?)?\d[\d,]*(?:\.\d+)?(?:%|ms|[xXkKmML]|\s?(?:LPA|lakh|crore|users))?(?![A-Za-z0-9])/g;

/** Numbers that appear in the bullet text, verbatim. Nothing is computed or invented. */
export function metricsIn(text: string): string[] {
  return [
    ...new Set((text.match(METRIC) ?? []).map((m) => m.trim()).filter(Boolean)),
  ].slice(0, 4);
}

/** Skills from the profile's own skill list that the bullet mentions. */
export function skillsIn(text: string, skills: string[]): string[] {
  const lower = text.toLowerCase();
  return skills.filter((sk) => {
    const k = sk.toLowerCase().trim();
    if (!k) return false;
    const esc = k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return new RegExp(`(^|[^a-z0-9])${esc}($|[^a-z0-9])`, "i").test(lower);
  });
}
