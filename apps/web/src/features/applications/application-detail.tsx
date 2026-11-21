"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Chip, StatusChip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { InputField, SelectField, TextareaField } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { copyFor } from "@/features/common/error-copy";
import { formatDateTime, humanize, siteLabel } from "@/features/common/format";
import { ApiError } from "@/lib/api/errors";
import {
  type Application,
  type FieldAnswer,
  isActive,
  useAnswerApplication,
  useApplication,
  useApplyRun,
  useCancelApplication,
} from "./hooks";
import { APPLY_ERRORS, STATUS_TONE, reasonText, statusLabel } from "./status";

export function ApplicationDetail({ id }: { id: string }) {
  const q = useApplication(id);
  if (q.isPending)
    return (
      <SkeletonGroup label="Loading the application" className="space-y-4">
        <Skeleton className="h-32 rounded-card" />
        <Skeleton className="h-40 rounded-card" />
      </SkeletonGroup>
    );
  if (q.isError) {
    const gone = q.error instanceof ApiError && q.error.status === 404;
    return (
      <ErrorState
        title={
          gone ? "Application not found" : "Couldn't load this application"
        }
        message={copyFor(q.error, APPLY_ERRORS)}
        onRetry={gone ? undefined : () => q.refetch()}
        retrying={q.isFetching}
      />
    );
  }
  return <Loaded app={q.data} />;
}

function Loaded({ app }: { app: Application }) {
  return (
    <div className="space-y-4">
      <Summary app={app} />
      {app.status === "waiting_for_user" && <AnswerForm app={app} />}
      {app.answers_used.length > 0 && <AnswersUsed app={app} />}
      <Screenshots app={app} />
    </div>
  );
}

function Summary({ app }: { app: Application }) {
  const cancel = useCancelApplication(app.id);
  const retry = useApplyRun();
  const { toast } = useToast();
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState<string>();
  const canRetry = ["skipped", "failed", "cancelled"].includes(app.status);

  return (
    <Card as="section" aria-labelledby="app-h" className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="app-h" className="text-section font-semibold">
            {app.title ?? "Untitled role"}
          </h2>
          {app.company && <p className="text-muted">{app.company}</p>}
        </div>
        <StatusChip tone={STATUS_TONE[app.status]}>
          {statusLabel(app.status)}
        </StatusChip>
      </div>
      <p role="status" aria-live="polite" className="text-muted">
        {app.status === "queued" &&
          "Waiting to start. This page updates by itself."}
        {app.status === "running" &&
          "Applying now. This page updates by itself."}
        {app.status === "waiting_for_user" && "Waiting for your answers below."}
        {app.status === "submitted" &&
          `Submitted${app.submitted_at ? ` on ${formatDateTime(app.submitted_at)}` : ""}.`}
        {app.status === "cancelled" && "Cancelled."}
      </p>
      {app.skip_reason && (
        <p className="rounded-control bg-warn-soft px-3 py-2 text-warn">
          <span className="font-semibold">Why: </span>
          {reasonText(app.skip_reason)}
        </p>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-hint">
        <dt className="text-subtle">Site</dt>
        <dd>
          {siteLabel(app.site)}
          {app.ats ? ` (${humanize(app.ats)})` : ""}
        </dd>
        <dt className="text-subtle">How</dt>
        <dd>
          {humanize(app.mode)}, via{" "}
          {app.channel === "extension"
            ? "your browser extension"
            : "our server"}
        </dd>
        <dt className="text-subtle">Attempts</dt>
        <dd className="font-mono tabular-nums">{app.attempts}</dd>
        <dt className="text-subtle">Updated</dt>
        <dd>{formatDateTime(app.updated_at)}</dd>
      </dl>
      <div className="flex flex-wrap items-center gap-2">
        <a
          href={app.direct_link}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center rounded-control border border-border-strong bg-surface px-4 font-medium hover:bg-surface-2 md:min-h-10"
        >
          {app.status === "submitted" ? "Open the job page" : "Apply yourself"}
          <span className="sr-only"> (opens in a new tab)</span>
        </a>
        {canRetry && (
          <Button
            loading={retry.isPending}
            onClick={() => {
              setError(undefined);
              retry.mutate(app.run_id, {
                onSuccess: () =>
                  toast({ kind: "info", title: "Application restarted" }),
                onError: (e) => setError(copyFor(e, APPLY_ERRORS)),
              });
            }}
          >
            Try again
          </Button>
        )}
        {isActive(app.status) && (
          <Button variant="danger" onClick={() => setConfirm(true)}>
            Cancel application
          </Button>
        )}
        <Link
          href="/applications"
          className="inline-flex min-h-11 items-center px-2 text-accent-text underline underline-offset-2"
        >
          All applications
        </Link>
      </div>
      {error && (
        <p role="alert" className="text-hint font-medium text-bad">
          {error}
        </p>
      )}
      <Modal
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Cancel this application?"
        description="Nothing more will be submitted. If the form was already sent, it stays submitted."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Keep it
            </Button>
            <Button
              variant="danger-solid"
              loading={cancel.isPending}
              onClick={() =>
                cancel.mutate(undefined, {
                  onSuccess: () => {
                    setConfirm(false);
                    toast({ kind: "info", title: "Application cancelled" });
                  },
                  onError: (e) => {
                    setConfirm(false);
                    setError(copyFor(e, APPLY_ERRORS));
                  },
                })
              }
            >
              Cancel application
            </Button>
          </>
        }
      />
    </Card>
  );
}

function AnswerForm({ app }: { app: Application }) {
  const answer = useAnswerApplication(app.id);
  const { toast } = useToast();
  const [values, setValues] = useState<Record<string, string>>({});
  const [remember, setRemember] = useState(true);
  const [missing, setMissing] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string>();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const miss = new Set(
      app.pending_fields
        .filter((f) => !values[f.key]?.trim())
        .map((f) => f.key),
    );
    setMissing(miss);
    if (miss.size) return;
    setError(undefined);
    const answers: FieldAnswer[] = app.pending_fields.map((f) => ({
      key: f.key,
      value: values[f.key].trim(),
      remember,
    }));
    answer.mutate(answers, {
      onSuccess: () =>
        toast({
          kind: "success",
          title: "Answers sent",
          description: "The application is resuming.",
        }),
      onError: (er) => setError(copyFor(er, APPLY_ERRORS)), // typed values stay in the form
    });
  }

  return (
    <Card as="section" aria-labelledby="ans-h">
      <h2 id="ans-h" className="text-section font-semibold">
        The form needs your answers
      </h2>
      <p className="text-muted">
        These required fields had no saved answer. Fill them in and the
        application continues.
      </p>
      <form onSubmit={submit} noValidate className="mt-3 space-y-4">
        {app.pending_fields.map((f) => {
          const common = {
            label: f.label,
            value: values[f.key] ?? "",
            error: missing.has(f.key) ? "This field is required." : undefined,
          };
          const set = (v: string) => setValues((s) => ({ ...s, [f.key]: v }));
          if (f.options.length > 0)
            return (
              <SelectField
                key={f.key}
                {...common}
                onChange={(e) => set(e.target.value)}
              >
                <option value="">Choose…</option>
                {f.options.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </SelectField>
            );
          if (f.kind === "textarea" || f.field_type === "long_text")
            return (
              <TextareaField
                key={f.key}
                {...common}
                maxLength={4000}
                onChange={(e) => set(e.target.value)}
              />
            );
          return (
            <InputField
              key={f.key}
              {...common}
              maxLength={4000}
              onChange={(e) => set(e.target.value)}
            />
          );
        })}
        <Checkbox
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
          label="Remember these answers for future applications"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" loading={answer.isPending}>
            Send answers and continue
          </Button>
        </div>
        {error && (
          <p role="alert" className="text-hint font-medium text-bad">
            {error}
          </p>
        )}
      </form>
    </Card>
  );
}

function AnswersUsed({ app }: { app: Application }) {
  return (
    <Card as="section" aria-labelledby="used-h">
      <h2 id="used-h" className="text-section font-semibold">
        Answers used
      </h2>
      <ul className="mt-3 divide-y divide-border">
        {app.answers_used.map((a, i) => {
          const label = String(a.label ?? a.key ?? `Field ${i + 1}`);
          return (
            <li
              key={`${i}-${label}`}
              className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 py-2.5 first:pt-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="text-hint text-subtle">{label}</p>
                <p className="break-words">{String(a.value ?? "")}</p>
              </div>
              <div className="flex gap-1.5">
                {a.required === true && <Chip>Required</Chip>}
                {typeof a.source === "string" && (
                  <Chip>{humanize(a.source)}</Chip>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function Screenshots({ app }: { app: Application }) {
  if (app.screenshots.length === 0) return null;
  return (
    <Card as="section" aria-labelledby="shots-h">
      <h2 id="shots-h" className="text-section font-semibold">
        Screenshots
      </h2>
      <p className="text-hint text-subtle">
        Links expire after 5 minutes. Reload this page for fresh ones.
      </p>
      <ul className="mt-2 space-y-1">
        {app.screenshots.map((url, i) => (
          <li key={url}>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2 md:min-h-8"
            >
              Screenshot {i + 1}
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          </li>
        ))}
      </ul>
    </Card>
  );
}
