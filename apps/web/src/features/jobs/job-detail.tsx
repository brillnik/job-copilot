"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Card } from "@/components/ui/card";
import {
  MetricChip,
  RedFlagChip,
  SkillChip,
  StatusChip,
} from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { ScoreBar } from "@/components/ui/score-bar";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/shell/page-header";
import { useSettings } from "@/hooks/use-settings";
import { ApiError, errorMessage } from "@/lib/api/errors";
import { patchJob } from "./api";
import { fitChips } from "./fit";
import { formatCtc, STATUS_LABEL, STATUS_TONE } from "./format";
import { jobKey, jobsKey, useBulletTexts, useJob } from "./hooks";
import { MustChips } from "./musts";
import { PastePanel } from "./paste-panel";
import { TailorPanel } from "./tailor-panel";
import { useJobEvents } from "./use-job-events";
import type { JobDetail, JobDescription } from "./types";

type Length = "auto" | "1" | "2" | "3";
const LENGTHS = [
  { value: "1", label: "1 page" },
  { value: "2", label: "2 pages" },
  { value: "3", label: "3 pages" },
  { value: "auto", label: "Auto" },
] as const;
const toLength = (n: number | null | undefined): Length =>
  n === 1 || n === 2 || n === 3 ? (String(n) as Length) : "auto";

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card as="section" aria-labelledby={id} className="flex flex-col gap-3">
      <h2 id={id} className="text-section font-semibold">
        {title}
      </h2>
      {children}
    </Card>
  );
}

function PageLength({ detail }: { detail: JobDetail }) {
  const qc = useQueryClient();
  const patch = useMutation({
    mutationFn: (v: Length) =>
      patchJob(detail.job.id, {
        max_pages_override: v === "auto" ? null : (Number(v) as 1 | 2 | 3),
      }),
    onSuccess: (data) => {
      qc.setQueryData(jobKey(detail.job.id), data);
      void qc.invalidateQueries({ queryKey: jobsKey });
    },
  });
  const value = patch.isPending
    ? (patch.variables as Length)
    : toLength(detail.job.max_pages_override);
  const asked = detail.jd?.requested_resume_pages;
  return (
    <Section id="length-h" title="Resume length">
      <Segmented<Length>
        label="Resume length"
        options={LENGTHS}
        value={value}
        onChange={(v) => patch.mutate(v)}
        className="self-start"
      />
      <p className="text-hint text-subtle">
        Applies to the next tailoring run.{" "}
        {value === "auto"
          ? asked
            ? `Auto follows your default; this posting asks for ${asked} page${asked > 1 ? "s" : ""}.`
            : "Auto follows your default length."
          : null}
      </p>
      <p role="status" aria-live="polite" className="text-hint">
        {patch.isSuccess && !patch.isPending && (
          <span className="text-ok">Saved.</span>
        )}
        {patch.isError && (
          <span role="alert" className="text-bad">
            Couldn&apos;t save: {errorMessage(patch.error)}
          </span>
        )}
      </p>
    </Section>
  );
}

function Facts({ jd }: { jd: JobDescription }) {
  const ctc = formatCtc(jd.ctc_lpa_min, jd.ctc_lpa_max);
  const exp =
    jd.experience_years_min != null || jd.experience_years_max != null
      ? [jd.experience_years_min, jd.experience_years_max]
          .filter((x) => x != null)
          .join("–")
      : null;
  const rows: [string, React.ReactNode][] = [
    ["Location", jd.location],
    ["Work mode", jd.work_mode !== "unknown" ? jd.work_mode : null],
    ["CTC", ctc && <span className="font-mono tabular-nums">{ctc}</span>],
    [
      "Experience",
      exp && <span className="font-mono tabular-nums">{exp} years</span>,
    ],
    ["Seniority", jd.seniority],
  ];
  const shown = rows.filter(([, v]) => v);
  if (shown.length === 0) return null;
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 md:grid-cols-3">
      {shown.map(([k, v]) => (
        <div key={k}>
          <dt className="text-hint text-subtle">{k}</dt>
          <dd className="capitalize">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function DetailSkeleton() {
  return (
    <SkeletonGroup label="Loading the job">
      <Skeleton className="mb-2 h-3.5 w-24" />
      <Skeleton className="mb-6 h-7 w-80 max-w-full" />
      <div className="grid gap-4 md:grid-cols-[1fr_380px]">
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    </SkeletonGroup>
  );
}

export function JobDetailScreen({ jobId }: { jobId: string }) {
  const qc = useQueryClient();
  const q = useJob(jobId);
  const settings = useSettings();
  const bullets = useBulletTexts();
  useJobEvents();

  if (q.isPending) return <DetailSkeleton />;
  if (q.isError || !q.data) {
    const notFound = q.error instanceof ApiError && q.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Job not found" : "Couldn't load this job"}
        message={
          notFound
            ? "It may have been deleted, or it belongs to another account."
            : errorMessage(q.error)
        }
        onRetry={notFound ? undefined : () => void q.refetch()}
        retrying={q.isRefetching}
      />
    );
  }

  const detail = q.data;
  const { job, jd } = detail;
  const prefs = settings.data?.preferences;
  const fit = fitChips(jd, prefs);
  const flags = job.red_flags;
  const title = jd?.title ?? job.title ?? "Untitled role";
  const company = jd?.company ?? job.company ?? "Company unknown";
  const needsText = job.status === "needs_paste" || job.status === "failed";

  return (
    <>
      <Link
        href="/"
        className="mb-3 inline-flex min-h-11 items-center gap-1 rounded-control text-muted hover:text-text md:min-h-8"
      >
        <span aria-hidden="true">←</span> Back to inbox
      </Link>
      <PageHeader
        level="screen"
        eyebrow={company}
        title={title}
        actions={
          <>
            <StatusChip tone={STATUS_TONE[job.status]}>
              {STATUS_LABEL[job.status]}
            </StatusChip>
            {job.url && (
              <a
                href={job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-h-11 items-center rounded-control border border-border-strong bg-surface px-3 text-[13px] font-medium hover:bg-surface-2 md:min-h-8"
              >
                Original posting
                <span className="sr-only"> (opens in a new tab)</span>
              </a>
            )}
          </>
        }
      />
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4 max-md:order-2">
          {job.status === "processing" && !jd && (
            <Card>
              <SkeletonGroup label="Reading the posting">
                <p className="mb-3 font-medium">Reading the posting…</p>
                <Skeleton className="mb-2 h-4 w-full" />
                <Skeleton className="mb-2 h-4 w-5/6" />
                <Skeleton className="h-4 w-2/3" />
              </SkeletonGroup>
            </Card>
          )}
          {needsText && (
            <Card>
              <PastePanel
                idPrefix="detail"
                failed={job.status === "failed"}
                reason={job.status_reason}
                onSubmit={async (text) => {
                  try {
                    const data = await patchJob(job.id, { text });
                    qc.setQueryData(jobKey(job.id), data);
                  } catch (e) {
                    throw new Error(errorMessage(e));
                  }
                  void qc.invalidateQueries({ queryKey: ["jobs"] });
                }}
              />
            </Card>
          )}

          {job.score !== null && (
            <Section id="match-h" title="Match">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <ScoreBar
                  score={job.score}
                  label="Match score"
                  className="w-full max-w-sm"
                />
                {detail.musts.length > 0 && (
                  <MetricChip>
                    {detail.musts.filter((m) => m.status === "have").length} of{" "}
                    {detail.musts.length} must-haves
                  </MetricChip>
                )}
              </div>
              {fit.length > 0 && (
                <ul
                  className="flex flex-wrap gap-2"
                  aria-label="Fit with your preferences"
                >
                  {fit.map((c) => (
                    <li key={c.key}>
                      <StatusChip
                        tone={c.tone}
                        className="h-auto py-1 whitespace-normal!"
                      >
                        {c.text}
                      </StatusChip>
                    </li>
                  ))}
                </ul>
              )}
            </Section>
          )}

          {flags.length > 0 && (
            <Section id="flags-h" title="Red flags">
              <ul className="flex flex-col gap-2">
                {flags.map((f) => (
                  <li key={f}>
                    <RedFlagChip className="h-auto py-1 whitespace-normal!">
                      {f}
                    </RedFlagChip>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {detail.musts.length > 0 && (
            <Section id="musts-h" title="Must-haves">
              <MustChips musts={detail.musts} bulletTexts={bullets.data} />
            </Section>
          )}

          {jd && (
            <Section id="jd-h" title="About the role">
              <Facts jd={jd} />
              {jd.responsibilities.length > 0 && (
                <div>
                  <h3 className="mb-1 font-semibold">Responsibilities</h3>
                  <ul className="list-disc space-y-1 pl-5">
                    {jd.responsibilities.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                </div>
              )}
              {jd.must_have.length > 0 && (
                <div>
                  <h3 className="mb-1 font-semibold">Required</h3>
                  <ul className="flex flex-wrap gap-2">
                    {jd.must_have.map((s) => (
                      <li key={s}>
                        <SkillChip>{s}</SkillChip>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {jd.nice_to_have.length > 0 && (
                <div>
                  <h3 className="mb-1 font-semibold">Nice to have</h3>
                  <ul className="flex flex-wrap gap-2">
                    {jd.nice_to_have.map((s) => (
                      <li key={s}>
                        <SkillChip>{s}</SkillChip>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {jd.keywords.length > 0 && (
                <div>
                  <h3 className="mb-1 font-semibold">Keywords</h3>
                  <ul className="flex flex-wrap gap-2">
                    {jd.keywords.map((s) => (
                      <li key={s}>
                        <SkillChip>{s}</SkillChip>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Section>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-4 max-md:order-1 md:sticky md:top-4">
          <TailorPanel detail={detail} />
          <PageLength detail={detail} />
        </div>
      </div>
    </>
  );
}
