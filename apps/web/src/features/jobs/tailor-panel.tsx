"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MetricChip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { SkeletonGroup, Skeleton } from "@/components/ui/skeleton";
import { useSettings } from "@/hooks/use-settings";
import { errorMessage } from "@/lib/api/errors";
import { answerRun, cancelRun, tailorJob } from "./api";
import { jobKey, jobsKey, jobIsTailorable, runKey, useRun } from "./hooks";
import { QuestionCard } from "./question-card";
import { RedFlagDialog } from "./red-flag-dialog";
import { RunProgress } from "./run-progress";
import { dailyCapCopy, tailorProblem, type TailorProblem } from "./tailor-copy";
import { isActiveRun, type JobDetail } from "./types";

const REASONS: Record<string, string> = {
  llm_unreachable: "The writing service couldn't be reached.",
  agent_error: "The tailoring agent hit an error.",
  missing_input: "Some of the inputs were missing.",
};

export function TailorPanel({ detail }: { detail: JobDetail }) {
  const qc = useQueryClient();
  const { job } = detail;
  const settings = useSettings();
  const [localRunId, setLocalRunId] = useState<string | null>(null);
  const runId = localRunId ?? detail.latest_run?.id ?? null;
  const run = useRun(runId);
  const [problem, setProblem] = useState<TailorProblem | null>(null);
  const [flags, setFlags] = useState<string[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshAll = () => {
    void qc.invalidateQueries({ queryKey: jobKey(job.id) });
    void qc.invalidateQueries({ queryKey: jobsKey });
    void qc.invalidateQueries({ queryKey: ["runs"] });
    void qc.invalidateQueries({ queryKey: ["settings"] });
  };

  const start = useMutation({
    mutationFn: (confirm: boolean) => tailorJob(job.id, confirm),
    onSuccess: (id) => {
      setProblem(null);
      setFlags(null);
      setLocalRunId(id);
      refreshAll();
    },
    onError: (e) => {
      const p = tailorProblem(e, { resetsAt: settings.data?.cap_resets_at });
      if (p.code === "red_flags") {
        setFlags(p.redFlags?.length ? p.redFlags : job.red_flags);
        return;
      }
      setFlags(null);
      if (p.code === "run_in_progress" && p.runId) {
        setLocalRunId(p.runId);
        setProblem(null);
        setNotice(p.message);
        refreshAll();
        return;
      }
      setProblem(p);
      if (p.code === "daily_cap")
        void qc.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  const answer = useMutation({
    mutationFn: (answers: Parameters<typeof answerRun>[1]) =>
      answerRun(runId as string, answers),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: runKey(runId as string) }),
    onError: () =>
      void qc.invalidateQueries({ queryKey: runKey(runId as string) }),
  });
  const cancel = useMutation({
    mutationFn: () => cancelRun(runId as string),
    onSuccess: () => {
      setNotice(
        "The run was cancelled. It didn't count against your daily limit.",
      );
      refreshAll();
    },
    onError: (e) => {
      setProblem({ code: "cancel", message: errorMessage(e) });
      refreshAll();
    },
  });

  const used = settings.data?.runs_used_today;
  const cap = settings.data?.daily_cap;
  const atCap = used !== undefined && cap !== undefined && used >= cap;
  const runData = run.data;
  const status =
    runData?.status ?? (detail.latest_run?.status as string | undefined);
  const active = isActiveRun(status);

  function begin() {
    setProblem(null);
    setNotice(null);
    if (job.red_flags.length > 0) setFlags(job.red_flags);
    else start.mutate(false);
  }

  const startBlock = (label: string) =>
    !jobIsTailorable(job.status) ? (
      <p className="text-muted">
        {job.status === "archived"
          ? "This job is archived. Unarchive it to tailor a resume."
          : "Tailoring is available once the posting has been read."}
      </p>
    ) : (
      <div className="flex flex-col gap-2">
        <div>
          <Button
            variant="primary"
            onClick={begin}
            loading={start.isPending && !flags}
            disabled={atCap}
          >
            {label}
          </Button>
        </div>
        {atCap && used !== undefined && cap !== undefined ? (
          <p className="text-hint text-warn">
            {dailyCapCopy(used, cap, settings.data?.cap_resets_at)}
          </p>
        ) : (
          <p className="text-hint text-subtle">
            Each run uses one of your daily tailoring runs.
          </p>
        )}
      </div>
    );

  let body: React.ReactNode;
  if (runId && run.isPending) {
    body = (
      <SkeletonGroup label="Loading the tailoring run">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="mt-3 h-24 w-full" />
      </SkeletonGroup>
    );
  } else if (runId && run.isError && !runData) {
    body = (
      <ErrorState
        title="Couldn't load the run"
        message={errorMessage(run.error)}
        onRetry={() => void run.refetch()}
        retrying={run.isRefetching}
        className="py-6"
      />
    );
  } else if (runData && active) {
    body = (
      <div className="flex flex-col gap-4">
        <RunProgress
          key={runData.id}
          runId={runData.id}
          status={runData.status}
          currentStep={runData.current_step}
        />
        {runData.status === "waiting_for_user" &&
          runData.pending_questions.length > 0 && (
            <QuestionCard
              key={runData.pending_questions.map((q) => q.skill).join("|")}
              questions={runData.pending_questions}
              onSubmit={async (answers) => {
                try {
                  await answer.mutateAsync(answers);
                } catch (e) {
                  throw new Error(errorMessage(e));
                }
              }}
            />
          )}
        <div>
          <Button
            variant="danger"
            size="sm"
            loading={cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            Cancel run
          </Button>
        </div>
      </div>
    );
  } else if (runData && runData.status === "in_review") {
    body = (
      <div className="flex flex-col gap-3">
        <p className="font-medium">Your tailored draft is ready for review.</p>
        <div>
          <Link
            href={`/review/${runData.id}`}
            className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-body font-medium text-on-accent hover:bg-accent-hover md:min-h-10"
          >
            Open review
          </Link>
        </div>
      </div>
    );
  } else {
    const last = runData?.status;
    body = (
      <div className="flex flex-col gap-3">
        {last === "needs_attention" && (
          <p role="alert" className="rounded-control bg-bad-soft p-3 text-bad">
            The last run needs attention.{" "}
            {REASONS[runData?.status_reason ?? ""] ?? ""} You can try again; a
            new run uses one of your daily runs.
          </p>
        )}
        {last === "cancelled" && (
          <p className="text-muted">The last run was cancelled.</p>
        )}
        {last === "rejected" && (
          <p className="text-muted">The last draft was rejected.</p>
        )}
        {last === "approved" && (
          <p className="font-medium">The last draft was approved.</p>
        )}
        {startBlock(
          last === "needs_attention"
            ? "Try again"
            : last
              ? "Tailor again"
              : "Tailor resume",
        )}
      </div>
    );
  }

  return (
    <Card
      as="section"
      aria-labelledby="tailor-h"
      className="flex flex-col gap-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="tailor-h" className="text-section font-semibold">
          Tailor your resume
        </h2>
        {used !== undefined && cap !== undefined && (
          <MetricChip
            aria-label={`${used} of ${cap} tailoring runs used today`}
          >
            {used} of {cap} runs today
          </MetricChip>
        )}
      </div>
      <div aria-live="polite" className="flex flex-col gap-3">
        {notice && <p className="rounded-control bg-surface-2 p-3">{notice}</p>}
        {problem && (
          <p role="alert" className="rounded-control bg-bad-soft p-3 text-bad">
            {problem.message}{" "}
            {problem.fix && (
              <Link href={problem.fix.href} className="font-semibold underline">
                {problem.fix.label}
              </Link>
            )}
          </p>
        )}
      </div>
      {body}
      {runData && runData.iterations.length > 0 && (
        <div>
          <h3 className="mb-2 text-hint font-semibold text-muted">
            Iteration history
          </h3>
          <ol className="flex flex-col gap-1.5">
            {runData.iterations.map((it) => (
              <li key={it.iteration} className="flex gap-2 text-body">
                <span className="font-mono text-muted tabular-nums">
                  #{it.iteration}
                </span>
                <span>{it.outcome ?? "In progress"}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      <RedFlagDialog
        open={flags !== null}
        flags={flags ?? []}
        busy={start.isPending}
        onCancel={() => setFlags(null)}
        onConfirm={() => start.mutate(true)}
      />
    </Card>
  );
}
