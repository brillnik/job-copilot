"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { SourceChip, StatusChip } from "@/components/ui/chip";
import { DiffLine, type DiffSegment } from "@/components/ui/diff-line";
import { AlertIcon } from "@/components/ui/icons";
import { Textarea } from "@/components/ui/input";
import type { BulletReview, Violation } from "./api";

type Seg = BulletReview["diff"][number];

/** The server computes the word diff; we only split it into the two sides. */
export function splitDiff(
  bullet: Pick<BulletReview, "diff" | "source_text" | "tailored_text">,
): { master: DiffSegment[]; tailored: DiffSegment[] } {
  if (bullet.diff.length === 0) {
    return {
      master: [{ text: bullet.source_text ?? "", kind: "same" }],
      tailored: [{ text: bullet.tailored_text, kind: "same" }],
    };
  }
  const master = bullet.diff
    .filter((s: Seg) => s.op !== "add")
    .map((s: Seg): DiffSegment => ({
      text: s.text,
      kind: s.op === "del" ? "del" : "same",
    }));
  const tailored = bullet.diff
    .filter((s: Seg) => s.op !== "del")
    .map((s: Seg): DiffSegment => ({
      text: s.text,
      kind: s.op === "add" ? "ins" : "same",
    }));
  return { master, tailored };
}

export const BULLET_MAX = 1000;

export function BulletCard({
  bullet,
  editable,
  value,
  onChange,
  refused = [],
}: {
  bullet: BulletReview;
  editable: boolean;
  /** The user's unsaved text, if they changed it. */
  value?: string;
  onChange?: (text: string | undefined) => void;
  /** Violations that made the server refuse the last edit of this bullet. */
  refused?: Violation[];
}) {
  const [open, setOpen] = useState(false);
  const fieldId = useId();
  const { master, tailored } = splitDiff(bullet);
  const editing = value !== undefined;
  const empty = editing && value.trim() === "";

  return (
    <li className="flex flex-col gap-2 rounded-card-mobile border border-border bg-surface p-3 md:rounded-card md:p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SourceChip
          id={bullet.source_id}
          original={bullet.source_text ?? "Not available"}
        />
        {bullet.reverted && (
          <StatusChip tone="warn">Reverted to your original wording</StatusChip>
        )}
        {editing && <StatusChip tone="accent">Unsaved edit</StatusChip>}
      </div>
      <div className="flex flex-col gap-1">
        <DiffLine side="master" segments={master} />
        <DiffLine side="tailored" segments={tailored} />
      </div>
      {bullet.reverted && bullet.revert_reason && (
        <p className="text-hint text-muted">
          <span className="font-medium text-text">Why it was reverted: </span>
          {bullet.revert_reason}
        </p>
      )}
      {refused.map((v, i) => (
        <p
          key={`${v.code}-${i}`}
          role="alert"
          className="flex items-start gap-1.5 text-hint font-medium text-bad"
        >
          <AlertIcon className="mt-0.5 size-3.5 shrink-0" />
          <span>
            Not saved ({v.code}): {v.message}
            {v.term ? ` “${v.term}”` : ""}. Your text is still in the box below.
          </span>
        </p>
      ))}
      {editable && (
        <div>
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={open || editing}
            aria-controls={fieldId}
            onClick={() => setOpen((o) => !o)}
          >
            {open || editing ? "Hide editor" : "Edit this bullet"}
          </Button>
          {(open || editing) && (
            <div id={fieldId} className="mt-1">
              <label
                htmlFor={`${fieldId}-t`}
                className="mb-1.5 block text-[13px] font-medium"
              >
                Edit bullet {bullet.source_id}
              </label>
              <Textarea
                id={`${fieldId}-t`}
                value={value ?? bullet.tailored_text}
                maxLength={BULLET_MAX}
                aria-invalid={empty || refused.length > 0 || undefined}
                onChange={(e) =>
                  onChange?.(
                    e.target.value === bullet.tailored_text
                      ? undefined
                      : e.target.value,
                  )
                }
              />
              <div className="mt-1 flex items-center justify-between gap-2">
                <p className="text-hint text-subtle">
                  Every edit is fact-checked against your profile.
                  {empty && (
                    <span className="font-medium text-bad">
                      {" "}
                      A bullet can&apos;t be empty.
                    </span>
                  )}
                </p>
                {editing && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onChange?.(undefined)}
                  >
                    Undo edit
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
