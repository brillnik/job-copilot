"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MetricChip, StatusChip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { SelectField } from "@/components/ui/field";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { copyFor } from "@/features/common/error-copy";
import { formatDateTime, humanize, siteLabel } from "@/features/common/format";
import type { Application } from "./hooks";
import { useApplications } from "./hooks";
import {
  STATUSES,
  type ApplicationStatus,
  STATUS_TONE,
  reasonText,
  statusLabel,
} from "./status";

export function ApplicationList() {
  const [status, setStatus] = useState<ApplicationStatus | "">("");
  const q = useApplications(status);
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="space-y-4">
      <SelectField
        label="Status"
        value={status}
        onChange={(e) => setStatus(e.target.value as ApplicationStatus | "")}
        className="w-full sm:w-64"
      >
        <option value="">All applications</option>
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {statusLabel(s)}
          </option>
        ))}
      </SelectField>
      <div aria-live="polite">
        {q.isPending ? (
          <SkeletonGroup label="Loading applications" className="space-y-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-24 rounded-card" />
            ))}
          </SkeletonGroup>
        ) : q.isError && q.data === undefined ? (
          <ErrorState
            title="Couldn't load applications"
            message={copyFor(q.error)}
            onRetry={() => q.refetch()}
            retrying={q.isFetching}
          />
        ) : items.length === 0 ? (
          <EmptyState
            title={
              status
                ? `No ${statusLabel(status).toLowerCase()} applications`
                : "No applications yet"
            }
            description="Applications show up here when you apply to an approved resume, or when Autopilot applies for you."
            action={
              <Link
                href="/autopilot"
                className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2"
              >
                Set up Autopilot
              </Link>
            }
          />
        ) : (
          <>
            <ul className="space-y-3" aria-label="Applications">
              {items.map((a) => (
                <li key={a.id}>
                  <ApplicationRow app={a} />
                </li>
              ))}
            </ul>
            {q.hasNextPage && (
              <div className="mt-4 flex justify-center">
                <Button
                  loading={q.isFetchingNextPage}
                  onClick={() => q.fetchNextPage()}
                >
                  Load more
                </Button>
              </div>
            )}
            {q.isFetchNextPageError && (
              <p
                role="alert"
                className="mt-2 text-center text-hint font-medium text-bad"
              >
                {copyFor(q.error)}
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function ApplicationRow({ app }: { app: Application }) {
  return (
    <Card
      as="div"
      className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2"
    >
      <div className="min-w-0">
        <p className="font-semibold">
          <Link
            href={`/applications/${encodeURIComponent(app.id)}`}
            className="underline-offset-2 hover:underline"
          >
            {app.title ?? "Untitled role"}
            {app.company ? (
              <span className="font-normal text-muted"> · {app.company}</span>
            ) : null}
          </Link>
        </p>
        <p className="mt-0.5 text-hint text-subtle">
          {siteLabel(app.site)} · {humanize(app.mode)} · updated{" "}
          {formatDateTime(app.updated_at)}
        </p>
        {app.skip_reason && (
          <p className="mt-1 text-muted">{reasonText(app.skip_reason)}</p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {app.attempts > 1 && <MetricChip>{app.attempts} attempts</MetricChip>}
        <StatusChip tone={STATUS_TONE[app.status]}>
          {statusLabel(app.status)}
        </StatusChip>
      </div>
    </Card>
  );
}
