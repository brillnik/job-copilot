import { describe, expect, it } from "vitest";
import { MAX_RESUME_BYTES } from "./constants";
import { validateResumeFile } from "./resume-file";

describe("validateResumeFile", () => {
  it("accepts PDF and DOCX within the limit", () => {
    expect(validateResumeFile({ name: "cv.PDF", size: 10 })).toBeNull();
    expect(validateResumeFile({ name: "cv.docx", size: MAX_RESUME_BYTES })).toBeNull();
  });
  it("rejects images with a specific message (backend accepts PDF/DOCX only)", () => {
    expect(validateResumeFile({ name: "scan.png", size: 10 })).toMatch(/Images/);
    expect(validateResumeFile({ name: "scan.JPG", size: 10 })).toMatch(/Images/);
  });
  it("rejects other types, empty and oversize files", () => {
    expect(validateResumeFile({ name: "cv.doc", size: 10 })).toMatch(/\.doc/);
    expect(validateResumeFile({ name: "cv.txt", size: 10 })).toMatch(/Unsupported/);
    expect(validateResumeFile({ name: "cv.pdf", size: 0 })).toMatch(/empty/);
    expect(
      validateResumeFile({ name: "cv.pdf", size: MAX_RESUME_BYTES + 1 }),
    ).toMatch(/limit is 5 MB/);
  });
});
