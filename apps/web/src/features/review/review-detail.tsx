"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { RedFlagChip, SkillChip, StatusChip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { TextareaField } from "@/components/ui/field";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { ApiError, errorMessage } from "@/lib/api/errors";
import {
  type DraftEdit,
  type MaxPages,
  type RunDetail,
  type Violation,
  putDraft,
  reviewErrorMessage,
  runKey,
  runName,
  useApprove,
  useReject,
  useRegenerate,
  useRun,
} from "./api";
import { BULLET_MAX, BulletCard } from "./bullet-card";
import { CoveragePanel } from "./coverage-panel";
import { FactCheckPanel } from "./fact-check-panel";
import { PageFit } from "./page-fit";
import { PdfPreview } from "./pdf-preview";
import { RedFlagConfirmDialog } from "./regenerate-dialog";
import { RejectDialog } from "./reject-dialog";
import { RunStatusPanel, STATUS_LABEL, STATUS_TONE } from "./run-status";

type Edits = {
  summary?: string;
  cover_note?: string;
  bullets: Record<string, string>;
};
const noEdits: Edits = { bullets: {} };

const violationKey = (v: Violation) =>
  v.field === "bullet" && v.source_id ? `bullet:${v.source_id}` : v.field;

export function ReviewDetail({ runId }: { runId: string }) {
  const q = useRun(runId);
  if (q.isPending)
    return (
      <SkeletonGroup label="Loading draft">
        <Skeleton className="mb-4 h-9 w-72" />
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="flex flex-col gap-3">
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
            <Skeleton className="h-32" />
          </div>
          <Skeleton className="h-96" />
        </div>
      </SkeletonGroup>
    );
  if (q.isError) {
    const gone = q.error instanceof ApiError && q.error.status === 404;
    return (
      <ErrorState
        title={gone ? "Draft not found" : "Couldn't load this draft"}
        message={
          gone
            ? "It may have been deleted, or it isn't yours."
            : errorMessage(q.error)
        }
        onRetry={gone ? undefined : () => void q.refetch()}
        retrying={q.isFetching}
      />
    );
  }
  return <Loaded run={q.data} />;
}

function Loaded({ run }: { run: RunDetail }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { toast } = useToast();
  const approve = useApprove();
  const reject = useReject();
  const regen = useRegenerate();

  const reviewable = run.status === "in_review";
  const hasDraft = run.bullets.length > 0 || run.summary !== null;
  const showDraft =
    hasDraft && ["in_review", "approved", "rejected"].includes(run.status);

  const [edits, setEdits] = useState<Edits>(noEdits);
  const [refused, setRefused] = useState<Violation[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectError, setRejectError] = useState<string | undefined>();
  const [length, setLength] = useState<MaxPages>(
    run.max_pages === 1 || run.max_pages === 2 || run.max_pages === 3
      ? run.max_pages
      : 2,
  );
  const [flags, setFlags] = useState<string[] | null>(null);
  const [approveMsg, setApproveMsg] = useState("");

  const dirtyKeys = [
    ...(edits.summary !== undefined ? ["summary"] : []),
    ...(edits.cover_note !== undefined ? ["cover_note"] : []),
    ...Object.keys(edits.bullets).map((id) => `bullet:${id}`),
  ];
  const dirty = dirtyKeys.length > 0;
  const emptyBullet = Object.values(edits.bullets).some((t) => t.trim() === "");
  const refusedFor = (key: string) =>
    refused.filter((v) => violationKey(v) === key);

  async function save() {
    const body: DraftEdit = {};
    if (edits.summary !== undefined) body.summary = edits.summary;
    if (edits.cover_note !== undefined) body.cover_note = edits.cover_note;
    const bullets = Object.entries(edits.bullets).map(([source_id, text]) => ({
      source_id,
      text,
    }));
    if (bullets.length) body.bullets = bullets;
    setSaving(true);
    setSaveError(null);
    setStale(false);
    try {
      const out = await putDraft(run.id, run.draft_rev, body);
      qc.setQueryData(runKey(run.id), out.run);
      const blocked = out.violations.filter((v) => v.blocked);
      setRefused(blocked);
      // Applied fields leave the edit buffer; refused ones keep the user's text.
      setEdits((cur) => {
        const next: Edits = {
          bullets: { ...cur.bullets },
          summary: cur.summary,
          cover_note: cur.cover_note,
        };
        for (const a of out.applied) {
          if (a === "summary") delete next.summary;
          else if (a === "cover_note") delete next.cover_note;
          else if (a.startsWith("bullet:")) delete next.bullets[a.slice(7)];
        }
        return next;
      });
      const msg =
        `${out.applied.length} ${out.applied.length === 1 ? "edit" : "edits"} saved` +
        (blocked.length
          ? `, ${blocked.length} refused by the fact check.`
          : ". Re-rendering the PDF.");
      setSaveMsg(msg);
      if (out.applied.length)
        toast({ kind: blocked.length ? "info" : "success", title: msg });
    } catch (e) {
      if (e instanceof ApiError && e.isStaleWrite && e.code === "stale_write")
        setStale(true);
      else if (e instanceof ApiError && e.code === "invalid_state")
        void qc.invalidateQueries({ queryKey: runKey(run.id) });
      setSaveError(reviewErrorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  function onApprove() {
    setApproveMsg("");
    approve.mutate(run.id, {
      onSuccess: (a) => {
        setApproveMsg(`Approved as ${a.file_name}.`);
        toast({
          kind: "success",
          title: "Draft approved",
          description: a.file_name,
        });
      },
      onError: (e) => {
        setApproveMsg(reviewErrorMessage(e));
        toast({
          kind: "error",
          title: "Couldn't approve",
          description: reviewErrorMessage(e),
        });
      },
    });
  }

  function startRegenerate(confirmRedFlags = false) {
    regen.mutate(
      { id: run.id, maxPages: length, confirmRedFlags },
      {
        onSuccess: () => {
          setFlags(null);
          toast({
            kind: "success",
            title: "Regenerating",
            description: "A new draft is being prepared.",
          });
          router.push(`/jobs/${run.job_id}`);
        },
        onError: (e) => {
          if (e instanceof ApiError && e.code === "red_flags") {
            const d = e.details as { red_flags?: string[] } | null | undefined;
            setFlags(Array.isArray(d?.red_flags) ? d.red_flags : []);
            return;
          }
          setFlags(null);
          toast({
            kind: "error",
            title: "Couldn't regenerate",
            description: reviewErrorMessage(e),
          });
        },
      },
    );
  }

  const approvedLike = run.status === "approved";
  const canApprove = reviewable && run.has_pdf && !dirty && !saving;

  return (
    <>
      <PageHeader
        level="screen"
        eyebrow="Review"
        title={runName(run)}
        description={
          reviewable
            ? "Compare each line with your master profile, edit if you like, then approve."
            : undefined
        }
        actions={
          reviewable ? (
            <>
              <Button
                variant="danger"
                onClick={() => {
                  setRejectError(undefined);
                  setRejectOpen(true);
                }}
              >
                Reject
              </Button>
              <Button
                variant="primary"
                loading={approve.isPending}
                disabled={!canApprove}
                onClick={onApprove}
              >
                Approve
              </Button>
            </>
          ) : undefined
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusChip tone={STATUS_TONE[run.status]}>
          {STATUS_LABEL[run.status]}
        </StatusChip>
        {run.flagged && <RedFlagChip>Flagged</RedFlagChip>}
        {run.edited && <StatusChip>Edited by you</StatusChip>}
        <Link
          href={`/jobs/${run.job_id}`}
          className="text-body font-medium text-accent-text underline underline-offset-2"
        >
          View job
        </Link>
      </div>
      <div role="status" aria-live="polite" className="mb-4 min-h-0 text-body">
        {reviewable && !run.has_pdf && (
          <p className="text-muted">
            Rendering the PDF. Approve unlocks when it&apos;s ready.
          </p>
        )}
        {reviewable && run.has_pdf && dirty && (
          <p className="text-muted">Save your edits to approve.</p>
        )}
        {approveMsg && (
          <p
            className={
              approve.isError ? "font-medium text-bad" : "font-medium text-ok"
            }
          >
            {approveMsg}
          </p>
        )}
      </div>

      {!showDraft ? (
        <RunStatusPanel run={run} />
      ) : (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
          <div className="flex min-w-0 flex-col gap-4">
            {stale && (
              <Card
                role="alert"
                className="flex flex-col items-start gap-2 border-warn"
              >
                <p className="font-semibold">
                  This draft changed since you opened it.
                </p>
                <p className="text-muted">
                  Load the latest version. Your edits stay in the fields; save
                  again to apply them on top.
                </p>
                <Button
                  onClick={() => {
                    setStale(false);
                    setSaveError(null);
                    void qc.invalidateQueries({ queryKey: runKey(run.id) });
                  }}
                >
                  Load latest draft
                </Button>
              </Card>
            )}
            {!stale && saveError && (
              <p role="alert" className="font-medium text-bad">
                {saveError}
              </p>
            )}

            <Card
              as="section"
              aria-labelledby="sum-h"
              className="flex flex-col gap-3"
            >
              <h2 id="sum-h" className="text-section font-semibold">
                Summary
              </h2>
              <EditableProse
                label="Summary"
                saved={run.summary ?? ""}
                value={edits.summary}
                max={2000}
                editable={reviewable}
                refused={refusedFor("summary")}
                onChange={(v) => setEdits((e) => ({ ...e, summary: v }))}
              />
              {run.skills_order.length > 0 && (
                <div>
                  <h3 className="mb-1.5 text-hint font-semibold text-muted">
                    Skills order
                  </h3>
                  <ul className="flex flex-wrap gap-1.5">
                    {run.skills_order.map((s) => (
                      <li key={s}>
                        <SkillChip>{s}</SkillChip>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>

            <section aria-labelledby="bul-h" className="flex flex-col gap-3">
              <h2 id="bul-h" className="text-section font-semibold">
                Bullets ({run.bullets.length})
              </h2>
              <ul className="m-0 flex list-none flex-col gap-3 p-0">
                {run.bullets.map((b) => (
                  <BulletCard
                    key={b.source_id}
                    bullet={b}
                    editable={reviewable}
                    value={edits.bullets[b.source_id]}
                    refused={refusedFor(`bullet:${b.source_id}`)}
                    onChange={(t) =>
                      setEdits((e) => {
                        const bullets = { ...e.bullets };
                        if (t === undefined) delete bullets[b.source_id];
                        else bullets[b.source_id] = t.slice(0, BULLET_MAX);
                        return { ...e, bullets };
                      })
                    }
                  />
                ))}
              </ul>
            </section>

            <Card
              as="section"
              aria-labelledby="cn-h"
              className="flex flex-col gap-3"
            >
              <h2 id="cn-h" className="text-section font-semibold">
                Cover note
              </h2>
              <EditableProse
                label="Cover note"
                saved={run.cover_note ?? ""}
                value={edits.cover_note}
                max={4000}
                editable={reviewable}
                refused={refusedFor("cover_note")}
                onChange={(v) => setEdits((e) => ({ ...e, cover_note: v }))}
              />
            </Card>

            {reviewable && (
              <div className="sticky bottom-20 z-10 flex flex-wrap items-center gap-3 rounded-card border border-border-strong bg-surface p-3 shadow-lg md:bottom-4">
                <Button
                  variant="primary"
                  loading={saving}
                  disabled={!dirty || emptyBullet}
                  onClick={() => void save()}
                >
                  Save {dirty ? `${dirtyKeys.length} ` : ""}
                  {dirtyKeys.length === 1 ? "edit" : "edits"}
                </Button>
                {dirty && (
                  <Button
                    variant="ghost"
                    onClick={() => {
                      setEdits(noEdits);
                      setRefused([]);
                    }}
                  >
                    Discard
                  </Button>
                )}
                <p
                  role="status"
                  aria-live="polite"
                  className="min-w-0 flex-1 text-hint text-muted"
                >
                  {saveMsg ||
                    (dirty
                      ? `${dirtyKeys.length} unsaved`
                      : "No unsaved edits")}
                </p>
              </div>
            )}
          </div>

          <aside
            className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-4"
            aria-label="Draft checks"
          >
            <FactCheckPanel
              violations={run.violations}
              flagged={run.flagged}
              refused={refused}
            />
            {run.coverage && (
              <CoveragePanel
                covered={run.coverage.covered ?? []}
                missing={run.coverage.missing ?? []}
                pct={run.coverage.pct ?? 0}
              />
            )}
            <PageFit
              count={run.pages?.count ?? null}
              lastPageFill={run.pages?.last_page_fill ?? 0}
              maxPages={run.max_pages}
              length={length}
              onLengthChange={setLength}
              onRegenerate={() => startRegenerate(false)}
              regenerating={regen.isPending && !flags}
              canRegenerate={
                run.status !== "queued" && run.status !== "running"
              }
            />
            {approvedLike ? (
              <PdfPreview runId={run.id} which="approved" ready rev={null} />
            ) : (
              <PdfPreview
                runId={run.id}
                which="latest"
                ready={run.has_pdf}
                rev={run.draft_rev}
              />
            )}
          </aside>
        </div>
      )}

      <RejectDialog
        open={rejectOpen}
        onClose={() => setRejectOpen(false)}
        pending={reject.isPending}
        error={rejectError}
        onSubmit={({ reasons, note }) => {
          setRejectError(undefined);
          reject.mutate(
            { id: run.id, reasons, note },
            {
              onSuccess: () => {
                setRejectOpen(false);
                toast({ kind: "success", title: "Draft rejected" });
                router.push("/review");
              },
              onError: (e) => setRejectError(reviewErrorMessage(e)),
            },
          );
        }}
      />
      <RedFlagConfirmDialog
        open={flags !== null}
        flags={flags ?? []}
        pending={regen.isPending}
        onClose={() => setFlags(null)}
        onConfirm={() => startRegenerate(true)}
      />
    </>
  );
}

function EditableProse({
  label,
  saved,
  value,
  max,
  editable,
  refused,
  onChange,
}: {
  label: string;
  saved: string;
  value?: string;
  max: number;
  editable: boolean;
  refused: Violation[];
  onChange: (v: string | undefined) => void;
}) {
  if (!editable)
    return saved ? (
      <p className="whitespace-pre-wrap">{saved}</p>
    ) : (
      <p className="text-muted">Nothing here.</p>
    );
  const error = refused.length
    ? `Not saved: ${refused.map((v) => v.message).join(" ")} Your text is kept here.`
    : undefined;
  return (
    <TextareaField
      label={`Edit ${label.toLowerCase()}`}
      value={value ?? saved}
      maxLength={max}
      error={error}
      hint={
        value !== undefined
          ? "Unsaved edit. Fact-checked when you save."
          : undefined
      }
      onChange={(e) =>
        onChange(e.target.value === saved ? undefined : e.target.value)
      }
    />
  );
}
