"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  ComingSoonChip,
  MetricChip,
  SkillChip,
  StatusChip,
} from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import {
  approveDraft,
  approvedKey,
  draftKey,
  putDraft,
  useApprovedProfile,
  useDraftProfile,
  type ProfileData,
} from "@/hooks/use-profile";
import { useScreeningAnswers } from "@/hooks/use-screening-answers";
import { errorMessage } from "@/lib/api/errors";
import { BulletEditor } from "./bullet-editor";
import {
  addBullet,
  listBullets,
  metricsIn,
  replaceBullet,
  skillsIn,
  unapprovedBulletIds,
  type BulletRef,
} from "./profile-model";

const linkBtn =
  "inline-flex min-h-11 items-center justify-center rounded-control border border-accent bg-accent px-4 font-medium text-on-accent";

function BulletRow({
  r,
  skills,
  unapproved,
  onSave,
}: {
  r: BulletRef;
  skills: string[];
  unapproved: boolean;
  onSave: (text: string) => Promise<unknown>;
}) {
  const [editing, setEditing] = useState(false);
  const sk = skillsIn(r.bullet.text, skills);
  const nums = metricsIn(r.bullet.text);

  if (editing)
    return (
      <li className="py-3">
        <BulletEditor
          label={`Edit achievement at ${r.entryLabel}`}
          initial={r.bullet.text}
          onCancel={() => setEditing(false)}
          onSave={async (t) => {
            await onSave(t);
            setEditing(false);
          }}
        />
      </li>
    );
  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 flex-1">{r.bullet.text}</p>
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Edit: ${r.bullet.text.slice(0, 60)}`}
          onClick={() => setEditing(true)}
        >
          Edit
        </Button>
      </div>
      {(unapproved || sk.length > 0 || nums.length > 0) && (
        <div className="flex flex-wrap items-center gap-1.5">
          {unapproved && <StatusChip tone="warn">Unapproved</StatusChip>}
          {sk.length > 0 && (
            <ul aria-label="Skills mentioned" className="contents">
              {sk.map((s) => (
                <li key={s} className="contents">
                  <SkillChip>{s}</SkillChip>
                </li>
              ))}
            </ul>
          )}
          {nums.length > 0 && (
            <ul aria-label="Numbers in the text" className="contents">
              {nums.map((m) => (
                <li key={m} className="contents">
                  <MetricChip>{m}</MetricChip>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function EntryCard({
  title,
  entryId,
  rows,
  skills,
  unapproved,
  save,
}: {
  title: string;
  entryId: string;
  rows: BulletRef[];
  skills: string[];
  unapproved: Set<string>;
  save: (next: (d: ProfileData) => ProfileData) => Promise<unknown>;
}) {
  const [adding, setAdding] = useState(false);
  return (
    <Card as="section" className="flex flex-col">
      <h3 className="text-[15px] font-semibold">{title}</h3>
      {rows.length === 0 && !adding && (
        <p className="mt-1 text-muted">No achievements saved for this yet.</p>
      )}
      <ul className="divide-y divide-border">
        {rows.map((r) => (
          <BulletRow
            key={r.bullet.id}
            r={r}
            skills={skills}
            unapproved={unapproved.has(r.bullet.id)}
            onSave={(t) => save((d) => replaceBullet(d, r.bullet.id, t))}
          />
        ))}
      </ul>
      {adding ? (
        <div className="mt-2">
          <BulletEditor
            label={`New achievement at ${title}`}
            onCancel={() => setAdding(false)}
            onSave={async (t) => {
              await save((d) => addBullet(d, entryId, t));
              setAdding(false);
            }}
          />
        </div>
      ) : (
        <div className="mt-2">
          <Button size="sm" onClick={() => setAdding(true)}>
            Add achievement
          </Button>
        </div>
      )}
    </Card>
  );
}

function RememberedAnswers() {
  const q = useScreeningAnswers();
  return (
    <section aria-labelledby="answers-h" className="flex flex-col gap-3">
      <h2 id="answers-h" className="text-section font-semibold">
        Remembered answers
      </h2>
      {q.isPending ? (
        <SkeletonGroup label="Loading remembered answers">
          <Skeleton className="h-16 w-full" />
        </SkeletonGroup>
      ) : q.isError ? (
        <ErrorState
          title="Couldn't load remembered answers"
          message={errorMessage(q.error)}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
        />
      ) : q.data.length === 0 ? (
        <EmptyState
          title="No remembered answers yet"
          description="When you answer an application question, we keep the answer here so you don't type it twice."
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {q.data.map((a) => (
            <Card as="li" key={a.id}>
              <p className="font-medium">{a.question}</p>
              <p className="mt-1 text-muted">{a.answer}</p>
              <StatusChip className="mt-2">Source: {a.source}</StatusChip>
            </Card>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ProfileView() {
  const qc = useQueryClient();
  const approved = useApprovedProfile();
  const draft = useDraftProfile();

  const saveDraft = useMutation({
    mutationFn: putDraft,
    onSuccess: (d) => qc.setQueryData(draftKey, d),
  });
  const approve = useMutation({
    mutationFn: approveDraft,
    onSuccess: (a) => {
      qc.setQueryData(approvedKey, a);
      qc.setQueryData(draftKey, null);
    },
  });

  const loading = approved.isPending || draft.isPending;
  const failed = approved.isError ? approved : draft.isError ? draft : null;

  const header = (extra?: React.ReactNode) => (
    <PageHeader
      title="Profile"
      description="The source of truth for every tailored resume."
      actions={extra}
    />
  );

  if (loading)
    return (
      <>
        {header()}
        <SkeletonGroup
          label="Loading your profile"
          className="flex flex-col gap-4"
        >
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </SkeletonGroup>
      </>
    );
  if (failed)
    return (
      <>
        {header()}
        <ErrorState
          title="Couldn't load your profile"
          message={errorMessage(failed.error)}
          onRetry={() => void failed.refetch()}
          retrying={failed.isFetching}
        />
      </>
    );

  const base = approved.data;
  const working = draft.data?.data ?? base?.data;
  if (!working)
    return (
      <>
        {header()}
        <EmptyState
          title="Your profile is empty"
          description="Upload a resume to build your master profile."
          action={
            <Link href="/onboarding/upload" className={linkBtn}>
              Upload a resume
            </Link>
          }
        />
      </>
    );

  const unapproved = unapprovedBulletIds(base?.data ?? null, working);
  const rows = listBullets(working);
  const skills = working.skills ?? [];
  // Edits always go through the draft; it is created from the approved profile on the first save.
  const save = (next: (d: ProfileData) => ProfileData) =>
    saveDraft.mutateAsync(next(working));
  const hasDraft = !!draft.data;

  return (
    <>
      {header(
        base ? (
          <StatusChip tone="ok">Approved · v{base.version}</StatusChip>
        ) : (
          <StatusChip tone="warn">Not approved yet</StatusChip>
        ),
      )}

      {hasDraft && (
        <div
          role="region"
          aria-label="Unapproved changes"
          className="mb-6 flex flex-col gap-3 rounded-card border border-warn bg-warn-soft p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <p className="text-warn">
            <span className="font-semibold">You have unapproved changes.</span>{" "}
            Tailored resumes only use approved bullets
            {unapproved.size > 0 ? ` (${unapproved.size} changed)` : ""}.
          </p>
          <Button
            variant="primary"
            loading={approve.isPending}
            onClick={() => approve.mutate()}
          >
            Approve changes
          </Button>
        </div>
      )}
      {approve.isError && (
        <div className="mb-6">
          <ErrorState
            title="Couldn't approve your changes"
            message={`${errorMessage(approve.error)} Your edits are still saved as a draft.`}
            onRetry={() => approve.mutate()}
            retrying={approve.isPending}
          />
        </div>
      )}

      <div className="flex flex-col gap-8">
        <section aria-labelledby="bank-h" className="flex flex-col gap-3">
          <div>
            <h2 id="bank-h" className="text-section font-semibold">
              Bullet bank
            </h2>
            <p className="mt-1 max-w-2xl text-hint text-subtle">
              {rows.length} {rows.length === 1 ? "achievement" : "achievements"}
              . Chips are detected here in your browser, not saved: skills from
              your list that appear in the text, and numbers exactly as written.
            </p>
          </div>
          {(working.experience ?? []).map((e) => (
            <EntryCard
              key={e.id}
              entryId={e.id!}
              title={[e.title, e.company].filter(Boolean).join(" at ")}
              rows={rows.filter((r) => r.entryId === e.id)}
              skills={skills}
              unapproved={unapproved}
              save={save}
            />
          ))}
          {(working.projects ?? []).map((p) => (
            <EntryCard
              key={p.id}
              entryId={p.id!}
              title={`Project: ${p.name}`}
              rows={rows.filter((r) => r.entryId === p.id)}
              skills={skills}
              unapproved={unapproved}
              save={save}
            />
          ))}
          {(working.experience ?? []).length +
            (working.projects ?? []).length ===
            0 && (
            <EmptyState
              title="No roles or projects yet"
              description="Add them by uploading a resume, then you can add achievements here."
            />
          )}
        </section>

        <section aria-labelledby="skills-h" className="flex flex-col gap-3">
          <h2 id="skills-h" className="text-section font-semibold">
            Skills
          </h2>
          {skills.length ? (
            <ul aria-label="Skills" className="flex flex-wrap gap-1.5">
              {skills.map((s) => (
                <li key={s}>
                  <SkillChip>{s}</SkillChip>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted">No skills listed.</p>
          )}
        </section>

        <RememberedAnswers />

        <section aria-labelledby="history-h" className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="history-h" className="text-section font-semibold">
              Version history
            </h2>
            <ComingSoonChip />
          </div>
          <p className="max-w-2xl text-muted">
            {base ? `You're on approved version ${base.version}. ` : ""}
            Browsing and restoring earlier versions isn&apos;t available yet.
          </p>
        </section>
      </div>
    </>
  );
}
