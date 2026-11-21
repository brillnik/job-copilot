import { describe, expect, it } from "vitest";
import type { ProfileData } from "@/hooks/use-profile";
import {
  EMPTY_PROFILE,
  addBullet,
  findFlags,
  metricsIn,
  replaceBullet,
  skillsIn,
  toFormValues,
  toProfileData,
  unapprovedBulletIds,
  unresolvedFlags,
} from "./profile-model";

const data: ProfileData = {
  contact: {
    name: "A",
    email: "a@b.co",
    phone: null,
    location: null,
    links: ["https://x.dev"],
  },
  summary: null,
  experience: [
    {
      id: "e1",
      company: "Acme",
      title: "SWE",
      location: null,
      start: "2020",
      end: null,
      bullets: [
        { id: "b1", text: "Cut p95 latency by 40% across 3 services" },
        { id: "b2", text: "Built React dashboards" },
      ],
    },
  ],
  projects: [
    {
      id: "p1",
      name: "Side",
      description: null,
      bullets: [{ id: "b3", text: "Shipped it" }],
    },
  ],
  education: [
    { id: "d1", institution: "IIT", degree: null, start: null, end: null },
  ],
  skills: ["React", "Go", "C++"],
};

describe("form <-> ProfileData", () => {
  it("round-trips, keeping ids and turning blanks into null", () => {
    expect(toProfileData(toFormValues(data))).toEqual(data);
  });
  it("omits ids for new bullets so the API assigns them", () => {
    const v = toFormValues(data);
    v.experience[0].bullets.push({ text: "  New thing  " });
    expect(toProfileData(v).experience![0].bullets![2]).toEqual({
      text: "New thing",
    });
  });
  it("splits skills on commas/newlines and dedupes", () => {
    const v = toFormValues(data);
    v.skillsText = "React, react\nGo,, ";
    expect(toProfileData(v).skills).toEqual(["React", "Go"]);
  });
});

describe("review flags", () => {
  it("flags missing and malformed values, and confirmation resolves them", () => {
    const v = toFormValues(data);
    const flags = findFlags(v);
    expect(flags.map((f) => f.path)).toEqual(["experience.0.end"]);
    v.contact.email = "nope";
    v.contact.name = "";
    const more = findFlags(v);
    expect(more.map((f) => f.path)).toEqual([
      "contact.name",
      "contact.email",
      "experience.0.end",
    ]);
    expect(
      unresolvedFlags(more, new Set(["contact.name", "experience.0.end"])).map(
        (f) => f.path,
      ),
    ).toEqual(["contact.email"]);
  });
  it("flags an empty draft", () => {
    const paths = findFlags(toFormValues(EMPTY_PROFILE)).map((f) => f.path);
    expect(paths).toEqual([
      "contact.name",
      "contact.email",
      "skillsText",
      "experience",
    ]);
  });
});

describe("profile page helpers", () => {
  it("replaces and adds bullets without touching ids", () => {
    const r = replaceBullet(data, "b2", "Built dashboards");
    expect(r.experience![0].bullets![1]).toEqual({
      id: "b2",
      text: "Built dashboards",
    });
    const a = addBullet(data, "p1", "Won an award");
    expect(a.projects![0].bullets).toEqual([
      { id: "b3", text: "Shipped it" },
      { text: "Won an award" },
    ]);
  });
  it("marks edited and new bullets as unapproved", () => {
    const draft = addBullet(
      replaceBullet(data, "b2", "Changed"),
      "e1",
      "Fresh",
    );
    const ids = unapprovedBulletIds(data, draft);
    expect([...ids].filter((i) => i === "b2")).toEqual(["b2"]);
    expect(ids.size).toBe(2);
    expect(unapprovedBulletIds(data, data).size).toBe(0);
  });
  it("only highlights numbers present in the text and skills already listed", () => {
    expect(metricsIn("Cut p95 latency by 40% across 3 services")).toEqual([
      "40%",
      "3",
    ]);
    expect(metricsIn("Built React dashboards")).toEqual([]);
    expect(
      skillsIn("Built React dashboards in C++ and Go", data.skills!),
    ).toEqual(["React", "Go", "C++"]);
    expect(skillsIn("Gopher", ["Go"])).toEqual([]);
  });
});
