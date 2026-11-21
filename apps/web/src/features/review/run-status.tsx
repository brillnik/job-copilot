import Link from "next/link";
import { Card } from "@/components/ui/card";
import { StatusChip, type StatusTone } from "@/components/ui/chip";
import type { RunDetail } from "./api";

type Status = RunDetail["status"];
export const STATUS_LABEL: Record<Status, string> = {
  queued: "Queued",
  running: "Running",
  waiting_for_user: "Waiting for you",
  in_review: "In review",
  approved: "Approved",
  rejected: "Rejected",
  needs_attention: "Needs attention",
  cancelled: "Cancelled",
};
export const STATUS_TONE: Record<Status, StatusTone> = {
  queued: "neutral",
  running: "accent",
  waiting_for_user: "warn",
  in_review: "accent",
  approved: "ok",
  rejected: "neutral",
  needs_attention: "bad",
  cancelled: "neutral",
};
const COPY: Partial<Record<Status, string>> = {
  queued:
    "This resume is queued. It will appear here for review when it's ready.",
  running: "This resume is being tailored. This page updates by itself.",
  waiting_for_user:
    "The tailoring step needs an answer from you before it can continue.",
  needs_attention: "The tailoring step stopped and needs your attention.",
  cancelled: "This run was cancelled.",
};

/** Run is not (yet) reviewable: explain, and point back to the job screen. */
export function RunStatusPanel({
  run,
}: {
  run: Pick<RunDetail, "status" | "status_reason" | "job_id" | "current_step">;
}) {
  return (
    <Card
      as="section"
      aria-labelledby="rs-h"
      className="flex flex-col items-start gap-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="rs-h" className="text-section font-semibold">
          Not ready for review
        </h2>
        <StatusChip tone={STATUS_TONE[run.status]}>
          {STATUS_LABEL[run.status]}
        </StatusChip>
      </div>
      <p role="status" aria-live="polite" className="text-muted">
        {COPY[run.status] ?? "This run can't be reviewed right now."}
        {run.current_step ? ` Current step: ${run.current_step}.` : ""}
        {run.status_reason ? ` ${run.status_reason}` : ""}
      </p>
      <Link
        href={`/jobs/${run.job_id}`}
        className="inline-flex min-h-11 items-center rounded-control border border-border-strong bg-surface px-4 text-body font-medium hover:bg-surface-2 md:min-h-10"
      >
        Go to the job
      </Link>
    </Card>
  );
}
