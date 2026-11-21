import { MAX_RESUME_BYTES } from "./constants";

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|heic)$/i;
const DOC_EXT = /\.(pdf|docx)$/i;

export const RESUME_ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** Returns an error message, or null when the file can be sent. */
export function validateResumeFile(file: {
  name: string;
  size: number;
}): string | null {
  if (IMAGE_EXT.test(file.name))
    return "Images aren't supported yet. Export your resume as a PDF or DOCX and upload that.";
  if (/\.doc$/i.test(file.name))
    return "Old .doc files aren't supported. Save it as DOCX or PDF and try again.";
  if (!DOC_EXT.test(file.name))
    return "Unsupported file type. Upload a PDF or DOCX resume.";
  if (file.size === 0) return "This file is empty. Choose a different file.";
  if (file.size > MAX_RESUME_BYTES)
    return `This file is ${(file.size / 1024 / 1024).toFixed(1)} MB. The limit is ${MAX_RESUME_BYTES / 1024 / 1024} MB.`;
  return null;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
