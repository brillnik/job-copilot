import type { JobStatus } from "./types";
import type { StatusTone } from "@/components/ui/chip";

export function formatCtc(min?: number | null, max?: number | null) {
  const f = (n: number) => String(Math.round(n * 10) / 10);
  if (min != null && max != null)
    return min === max ? `${f(min)} LPA` : `${f(min)}–${f(max)} LPA`;
  if (max != null) return `up to ${f(max)} LPA`;
  if (min != null) return `${f(min)}+ LPA`;
  return null;
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
  });
}

export const STATUS_LABEL: Record<JobStatus, string> = {
  processing: "Processing",
  needs_paste: "Needs text",
  new: "New",
  tailoring: "Tailoring",
  in_review: "In review",
  approved: "Approved",
  rejected: "Rejected",
  archived: "Archived",
  failed: "Failed",
};

export const STATUS_TONE: Record<JobStatus, StatusTone> = {
  processing: "neutral",
  needs_paste: "warn",
  new: "accent",
  tailoring: "accent",
  in_review: "accent",
  approved: "ok",
  rejected: "neutral",
  archived: "neutral",
  failed: "bad",
};
