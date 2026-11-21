"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Modal } from "@/components/ui/modal";
import { TextareaField } from "@/components/ui/field";
import type { RejectReason } from "./api";

export const REJECT_REASONS: { value: RejectReason; label: string }[] = [
  { value: "wrong_emphasis", label: "Wrong emphasis" },
  { value: "too_generic", label: "Too generic" },
  { value: "factual_issue", label: "Factual issue" },
  { value: "tone", label: "Tone is off" },
];

export function RejectDialog({
  open,
  onClose,
  onSubmit,
  pending,
  error,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (v: { reasons: RejectReason[]; note: string }) => void;
  pending?: boolean;
  /** Shown inside the dialog; the user's choices are kept on failure. */
  error?: string;
}) {
  const [reasons, setReasons] = useState<RejectReason[]>([]);
  const [note, setNote] = useState("");
  return (
    <Modal
      open={open}
      onClose={onClose}
      variant="sheet"
      title="Reject this draft"
      description="Tell us what was wrong so the next attempt is better. Both are optional."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="danger-solid"
            loading={pending}
            onClick={() => onSubmit({ reasons, note })}
          >
            Reject draft
          </Button>
        </>
      }
    >
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit({ reasons, note });
        }}
      >
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 text-[13px] font-medium">
            What was wrong?
          </legend>
          {REJECT_REASONS.map((r) => (
            <Checkbox
              key={r.value}
              label={r.label}
              checked={reasons.includes(r.value)}
              onChange={(e) =>
                setReasons((cur) =>
                  e.target.checked
                    ? [...cur, r.value]
                    : cur.filter((x) => x !== r.value),
                )
              }
              className="min-h-8 items-center text-body text-text"
            />
          ))}
        </fieldset>
        <TextareaField
          label="Note (optional)"
          value={note}
          maxLength={2000}
          onChange={(e) => setNote(e.target.value)}
        />
        <div role="alert" aria-live="assertive">
          {error && <p className="text-hint font-medium text-bad">{error}</p>}
        </div>
      </form>
    </Modal>
  );
}
