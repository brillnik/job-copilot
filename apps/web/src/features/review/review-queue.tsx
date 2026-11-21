"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MetricChip, RedFlagChip, StatusChip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { ReviewIcon } from "@/components/ui/icons";
import { ScoreBar } from "@/components/ui/score-bar";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { ApiError, errorMessage } from "@/lib/api/errors";
import {
  type RunSummary,
  reviewErrorMessage,
  runName,
  useApprove,
  useReject,
  useReviewQueue,
} from "./api";
import { RejectDialog } from "./reject-dialog";

export function QueueItem({
  run,
  onApprove,
  onReject,
  approving,
}: {
  run: RunSummary;
  onApprove: () => void;
  onReject: () => void;
  approving?: boolean;
}) {
  const name = runName(run);
  return (
    <Card as="li" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-section font-semibold">
            <Link
              href={`/review/${run.id}`}
              className="hover:underline focus-visible:underline"
            >
              {name}
            </Link>
          </h2>
          <p className="text-hint text-subtle">
            Created{" "}
            <time dateTime={run.created_at}>
              {new Date(run.created_at).toLocaleDateString()}
            </time>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {run.flagged && <RedFlagChip>Flagged</RedFlagChip>}
          {run.coverage && <MetricChip>Coverage {run.coverage}</MetricChip>}
          {run.pages !== null && (
            <MetricChip>
              {run.pages} {run.pages === 1 ? "page" : "pages"}
            </MetricChip>
          )}
        </div>
      </div>
      {run.score !== null && (
        <ScoreBar score={run.score} className="max-w-xs" />
      )}
      {(run.top_changes?.length ?? 0) > 0 && (
        <div>
          <p className="mb-1 text-hint font-semibold text-muted">Top changes</p>
          <ul className="flex list-disc flex-col gap-0.5 pl-5 text-body">
            {run.top_changes?.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Link
          href={`/review/${run.id}`}
          className="inline-flex min-h-11 items-center rounded-control border border-border-strong bg-surface px-4 text-body font-medium hover:bg-surface-2 md:min-h-10"
        >
          Open draft<span className="sr-only">: {name}</span>
        </Link>
        <Button
          variant="primary"
          loading={approving}
          onClick={onApprove}
          aria-label={`Approve ${name}`}
        >
          Approve
        </Button>
        <Button
          variant="danger"
          onClick={onReject}
          aria-label={`Reject ${name}`}
        >
          Reject
        </Button>
      </div>
    </Card>
  );
}

export function ReviewQueue() {
  const router = useRouter();
  const { toast } = useToast();
  const q = useReviewQueue();
  const approve = useApprove();
  const reject = useReject();
  const [announce, setAnnounce] = useState("");
  const [rejecting, setRejecting] = useState<RunSummary | null>(null);
  const [rejectError, setRejectError] = useState<string | undefined>();
  const [busy, setBusy] = useState<string | null>(null);

  const items = q.data?.pages.flatMap((p) => p.items) ?? [];

  function onApprove(run: RunSummary) {
    setBusy(run.id);
    approve.mutate(run.id, {
      onSuccess: () => {
        setAnnounce(`Approved ${runName(run)}.`);
        toast({
          kind: "success",
          title: "Draft approved",
          description: runName(run),
        });
      },
      onError: (e) => {
        if (e instanceof ApiError && e.code === "pdf_not_ready") {
          const msg =
            "The PDF is still rendering. Opening the draft so you can check it.";
          setAnnounce(msg);
          toast({ kind: "info", title: "PDF not ready yet", description: msg });
          router.push(`/review/${run.id}`);
          return;
        }
        setAnnounce(reviewErrorMessage(e));
        toast({
          kind: "error",
          title: "Couldn't approve",
          description: reviewErrorMessage(e),
        });
      },
      onSettled: () => setBusy(null),
    });
  }

  return (
    <>
      <PageHeader
        title="Review queue"
        description="Tailored drafts waiting for your approval."
      />
      <p role="status" aria-live="polite" className="sr-only">
        {announce}
      </p>
      {q.isPending ? (
        <SkeletonGroup
          label="Loading review queue"
          className="flex flex-col gap-3"
        >
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40 rounded-card" />
          ))}
        </SkeletonGroup>
      ) : q.isError ? (
        <ErrorState
          title="Couldn't load the review queue"
          message={errorMessage(q.error)}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<ReviewIcon />}
          title="Nothing to review"
          description="Drafts that need your approval will show up here."
          action={
            <Link
              href="/"
              className="inline-flex min-h-11 items-center rounded-control border border-border-strong bg-surface px-4 text-body font-medium hover:bg-surface-2"
            >
              Browse jobs
            </Link>
          }
        />
      ) : (
        <>
          <p className="mb-3 text-hint text-muted">
            <StatusChip tone="accent">
              {items.length}
              {q.hasNextPage ? "+" : ""} awaiting review
            </StatusChip>
          </p>
          <ul className="m-0 flex list-none flex-col gap-3 p-0">
            {items.map((r) => (
              <QueueItem
                key={r.id}
                run={r}
                approving={busy === r.id}
                onApprove={() => onApprove(r)}
                onReject={() => {
                  setRejectError(undefined);
                  setRejecting(r);
                }}
              />
            ))}
          </ul>
          {q.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button
                loading={q.isFetchingNextPage}
                onClick={() => void q.fetchNextPage()}
              >
                Load more
              </Button>
            </div>
          )}
          {q.isFetchNextPageError && (
            <p role="alert" className="mt-2 text-center font-medium text-bad">
              Couldn&apos;t load more drafts. Try again.
            </p>
          )}
        </>
      )}
      <RejectDialog
        open={rejecting !== null}
        onClose={() => setRejecting(null)}
        pending={reject.isPending}
        error={rejectError}
        onSubmit={({ reasons, note }) => {
          if (!rejecting) return;
          const run = rejecting;
          reject.mutate(
            { id: run.id, reasons, note },
            {
              onSuccess: () => {
                setRejecting(null);
                setAnnounce(`Rejected ${runName(run)}.`);
                toast({
                  kind: "success",
                  title: "Draft rejected",
                  description: runName(run),
                });
              },
              onError: (e) => setRejectError(reviewErrorMessage(e)),
            },
          );
        }}
      />
    </>
  );
}
