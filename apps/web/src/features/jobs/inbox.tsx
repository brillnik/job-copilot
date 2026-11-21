"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { MetricChip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { InboxIcon } from "@/components/ui/icons";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shell/page-header";
import { useSettings } from "@/hooks/use-settings";
import { errorMessage } from "@/lib/api/errors";
import { AddJobModal } from "./add-job-modal";
import { patchJob, tailorJob } from "./api";
import { DEFAULT_FILTERS, hasActiveFilters, InboxFilters } from "./filters";
import { jobKey, jobsKey, useJob, useJobList } from "./hooks";
import { JobRow } from "./job-row";
import { PastePanel } from "./paste-panel";
import { tailorProblem } from "./tailor-copy";
import { useJobEvents } from "./use-job-events";
import type { JobFilters, JobSummary } from "./types";

type TailorResult = {
  id: string;
  label: string;
  ok: boolean;
  message: string;
  fix?: { href: string; label: string };
};

const jobLabel = (j: JobSummary) =>
  `${j.title ?? "Untitled role"} at ${j.company ?? "unknown company"}`;

/** Connected paste box for a needs_paste / failed row. */
function RowPaste({ job }: { job: JobSummary }) {
  const qc = useQueryClient();
  // The list payload has no status_reason; fetch it for these (few) rows.
  const detail = useJob(job.id);
  return (
    <PastePanel
      idPrefix={`row-${job.id}`}
      failed={job.status === "failed"}
      reason={detail.data?.job.status_reason}
      onSubmit={async (text) => {
        try {
          await patchJob(job.id, { text });
        } catch (e) {
          throw new Error(errorMessage(e));
        }
        void qc.invalidateQueries({ queryKey: jobsKey });
        void qc.invalidateQueries({ queryKey: jobKey(job.id) });
      }}
    />
  );
}

function ListSkeleton() {
  return (
    <SkeletonGroup label="Loading your jobs">
      <ul className="flex flex-col gap-3">
        {[0, 1, 2].map((i) => (
          <li key={i}>
            <Card className="flex flex-col gap-3">
              <Skeleton className="h-3.5 w-24" />
              <Skeleton className="h-5 w-64 max-w-full" />
              <Skeleton className="h-3.5 w-48" />
              <Skeleton className="h-2 w-full max-w-xs" />
            </Card>
          </li>
        ))}
      </ul>
    </SkeletonGroup>
  );
}

export function Inbox() {
  const qc = useQueryClient();
  const [filters, setFilters] = useState<JobFilters>(DEFAULT_FILTERS);
  const [adding, setAdding] = useState(false);
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [results, setResults] = useState<TailorResult[] | null>(null);
  const [tailoring, setTailoring] = useState(false);
  const [announce, setAnnounce] = useState("");

  const list = useJobList(filters);
  const settings = useSettings();
  useJobEvents((types) => {
    const ready = types.filter((t) => t === "job_ready").length;
    const paste = types.filter((t) => t === "job_needs_paste").length;
    const failed = types.filter((t) => t === "job_failed").length;
    const parts = [
      ready && `${ready} job${ready > 1 ? "s" : ""} ready`,
      paste && `${paste} need${paste > 1 ? "" : "s"} pasted text`,
      failed && `${failed} failed to read`,
    ].filter(Boolean);
    if (parts.length) setAnnounce(parts.join(", "));
  });

  const items = useMemo(
    () => list.data?.pages.flatMap((p) => p.items) ?? [],
    [list.data],
  );
  const selectable = items.filter((j) => j.status === "new");
  // Rows that stopped being tailorable (refetch) silently leave the selection.
  const chosen = selectable.filter((j) => selected.has(j.id));
  const allChosen =
    selectable.length > 0 && chosen.length === selectable.length;

  function toggle(id: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function tailorSelected() {
    setTailoring(true);
    setResults(null);
    const out: TailorResult[] = [];
    const succeeded = new Set<string>();
    let capHit = false;
    for (const job of chosen) {
      const label = jobLabel(job);
      if (capHit) {
        out.push({
          id: job.id,
          label,
          ok: false,
          message: "Not started: the daily limit was reached.",
        });
        continue;
      }
      try {
        await tailorJob(job.id, false);
        succeeded.add(job.id);
        out.push({
          id: job.id,
          label,
          ok: true,
          message: "Tailoring started.",
        });
      } catch (e) {
        const p = tailorProblem(e, {
          resetsAt: settings.data?.cap_resets_at,
        });
        if (p.code === "daily_cap") capHit = true;
        out.push({
          id: job.id,
          label,
          ok: false,
          message:
            p.code === "red_flags"
              ? "This posting has red flags. Open the job to review them and confirm."
              : p.message,
          fix: p.fix,
        });
      }
    }
    // Only the jobs that started leave the selection; failures stay selected.
    setSelected(
      (prev) => new Set([...prev].filter((id) => !succeeded.has(id))),
    );
    setResults(out);
    setTailoring(false);
    void qc.invalidateQueries({ queryKey: jobsKey });
    void qc.invalidateQueries({ queryKey: ["runs"] });
    void qc.invalidateQueries({ queryKey: ["settings"] });
  }

  const loadError: unknown = list.isError ? list.error : null;
  const used = settings.data?.runs_used_today;
  const cap = settings.data?.daily_cap;

  return (
    <>
      <PageHeader
        title="Inbox"
        description="Jobs you've captured and tailored resumes in progress."
        actions={
          <>
            {used !== undefined && cap !== undefined && (
              <MetricChip
                aria-label={`${used} of ${cap} tailoring runs used today`}
              >
                {used} of {cap} runs today
              </MetricChip>
            )}
            <Button variant="primary" onClick={() => setAdding(true)}>
              Add job
            </Button>
          </>
        }
      />
      <AddJobModal open={adding} onClose={() => setAdding(false)} />
      <InboxFilters filters={filters} onChange={setFilters} />

      <div aria-live="polite" role="status" className="sr-only">
        {announce}
      </div>

      {selectable.length > 0 && (
        <div className="sticky top-0 z-10 mb-3 flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-3">
          <Checkbox
            label={
              chosen.length > 0
                ? `${chosen.length} selected`
                : "Select all new jobs"
            }
            checked={allChosen}
            onChange={(e) =>
              setSelected(
                e.target.checked
                  ? new Set(selectable.map((j) => j.id))
                  : new Set(),
              )
            }
            className="items-center text-body font-medium text-text"
          />
          <Button
            variant="primary"
            size="sm"
            disabled={chosen.length === 0}
            loading={tailoring}
            onClick={tailorSelected}
          >
            Tailor selected{chosen.length > 0 ? ` (${chosen.length})` : ""}
          </Button>
        </div>
      )}

      <div aria-live="polite">
        {results && (
          <Card
            as="section"
            aria-labelledby="tailor-results-h"
            className="mb-3"
          >
            <div className="flex items-start justify-between gap-3">
              <h2 id="tailor-results-h" className="text-section font-semibold">
                Tailoring results
              </h2>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setResults(null)}
              >
                Dismiss
              </Button>
            </div>
            <ul className="mt-2 flex flex-col gap-2">
              {results.map((r) => (
                <li key={r.id} className="text-body">
                  <span className="font-medium">{r.label}</span>
                  <span className="text-muted">
                    {" "}
                    · {r.ok ? "Started" : "Not started"}: {r.message}
                  </span>{" "}
                  {r.fix && (
                    <Link
                      href={r.fix.href}
                      className="font-medium text-accent-text underline"
                    >
                      {r.fix.label}
                    </Link>
                  )}
                  {!r.ok && (
                    <>
                      {" "}
                      <Link
                        href={`/jobs/${r.id}`}
                        className="font-medium text-accent-text underline"
                      >
                        Open job
                      </Link>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      {list.isPending ? (
        <ListSkeleton />
      ) : list.isError ? (
        <ErrorState
          title="Couldn't load your jobs"
          message={errorMessage(loadError)}
          onRetry={() => void list.refetch()}
          retrying={list.isRefetching}
        />
      ) : items.length === 0 ? (
        hasActiveFilters(filters) ? (
          <EmptyState
            icon={<InboxIcon className="size-6" />}
            title="No jobs match these filters"
            description="Try a lower minimum score or clear the filters."
            action={
              <Button onClick={() => setFilters({ sort: filters.sort })}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            icon={<InboxIcon className="size-6" />}
            title="Nothing in your inbox yet"
            description="Add a job by link, pasted text or a screenshot to get a match score and a tailored resume."
            action={
              <Button variant="primary" onClick={() => setAdding(true)}>
                Add your first job
              </Button>
            }
          />
        )
      ) : (
        <>
          <ul className="flex flex-col gap-3" aria-label="Jobs">
            {items.map((job) => (
              <JobRow
                key={job.id}
                job={job}
                selected={
                  job.status === "new" ? selected.has(job.id) : undefined
                }
                onSelect={(on) => toggle(job.id, on)}
              >
                {job.status === "needs_paste" || job.status === "failed" ? (
                  <RowPaste job={job} />
                ) : undefined}
              </JobRow>
            ))}
          </ul>
          {list.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button
                onClick={() => void list.fetchNextPage()}
                loading={list.isFetchingNextPage}
              >
                Load more
              </Button>
            </div>
          )}
          {loadError != null && (
            <p role="alert" className="mt-3 text-center text-bad">
              Couldn&apos;t refresh your jobs. {errorMessage(loadError)}
            </p>
          )}
        </>
      )}
    </>
  );
}
