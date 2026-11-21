import Link from "next/link";
import { Checkbox } from "@/components/ui/checkbox";
import { Card } from "@/components/ui/card";
import { MetricChip, RedFlagChip, StatusChip } from "@/components/ui/chip";
import { ScoreBar } from "@/components/ui/score-bar";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCtc, formatDate, STATUS_LABEL, STATUS_TONE } from "./format";
import type { JobSummary } from "./types";

/**
 * One inbox row. `children` replaces the score column for rows that need an
 * action (the paste box for needs_paste / failed).
 */
export function JobRow({
  job,
  selected,
  onSelect,
  children,
}: {
  job: JobSummary;
  /** undefined = row is not selectable. */
  selected?: boolean;
  onSelect?: (selected: boolean) => void;
  children?: React.ReactNode;
}) {
  const name = `${job.title ?? "Untitled role"} at ${job.company ?? "unknown company"}`;
  const ctc = formatCtc(job.ctc_lpa_min, job.ctc_lpa_max);
  const processing = job.status === "processing";
  return (
    <Card as="li" className="flex gap-3" data-status={job.status}>
      <div className="flex-none">
        {selected !== undefined ? (
          <Checkbox
            label={<span className="sr-only">Select {name}</span>}
            checked={selected}
            onChange={(e) => onSelect?.(e.target.checked)}
            className="-m-2 size-11 items-center justify-center md:m-0 md:size-8"
          />
        ) : (
          <span className="block size-6" aria-hidden="true" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div className="min-w-0">
            {processing && !job.title ? (
              <>
                <p className="font-semibold">Reading the posting…</p>
                <div aria-hidden="true" className="mt-2 flex flex-col gap-2">
                  <Skeleton className="h-3.5 w-48" />
                  <Skeleton className="h-3.5 w-32" />
                </div>
              </>
            ) : (
              <>
                <p className="text-hint text-muted">
                  {job.company ?? "Company unknown"}
                </p>
                <h3 className="text-section font-semibold">
                  <Link
                    href={`/jobs/${job.id}`}
                    className="rounded-control hover:underline"
                  >
                    {job.title ?? "Untitled role"}
                  </Link>
                </h3>
              </>
            )}
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-hint text-muted">
              {job.location && <span>{job.location}</span>}
              {ctc && <span className="font-mono tabular-nums">{ctc}</span>}
              <span>Added {formatDate(job.created_at)}</span>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {job.red_flags.length > 0 && (
              <RedFlagChip>
                {job.red_flags.length === 1
                  ? "1 red flag"
                  : `${job.red_flags.length} red flags`}
              </RedFlagChip>
            )}
            <StatusChip tone={STATUS_TONE[job.status]}>
              {STATUS_LABEL[job.status]}
            </StatusChip>
          </div>
        </div>
        {children ? (
          <div className="mt-3">{children}</div>
        ) : job.score !== null ? (
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <ScoreBar
              score={job.score}
              label={`Match for ${name}`}
              className="w-full max-w-xs"
            />
            {job.musts_summary && (
              <MetricChip>{job.musts_summary} must-haves</MetricChip>
            )}
          </div>
        ) : null}
      </div>
    </Card>
  );
}
