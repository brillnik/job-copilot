"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { MetricChip } from "@/components/ui/chip";
import { Modal } from "@/components/ui/modal";
import { SelectField, TextareaField, InputField } from "@/components/ui/field";
import {
  COLUMNS,
  type Column,
  type TrackerCard,
  previewIsComplete,
  trackerErrorMessage,
  useRemoveCard,
  useUpdateCard,
} from "./api";
import { useToast } from "@/components/ui/toast";

const NOTE_MAX = 10000;
const dateInput = (iso: string | null) => (iso ? iso.slice(0, 10) : "");

/**
 * Details for one card: stage (touch-friendly alternative to dragging), applied date and notes.
 * Notes: the board only carries a 120-char preview and the API has no GET /tracker/{id}, so
 * the full text is known only when the preview is complete or after a save in this session.
 */
export function CardDialog({
  card,
  knownNotes,
  onClose,
  onMove,
}: {
  card: TrackerCard;
  /** Full notes if known (preview was complete, or saved earlier this session); else undefined. */
  knownNotes: string | null | undefined;
  onClose: () => void;
  onMove: (column: Column) => void;
}) {
  const { toast } = useToast();
  const update = useUpdateCard();
  const remove = useRemoveCard();
  const complete =
    knownNotes !== undefined || previewIsComplete(card.notes_preview);
  const initialNotes =
    knownNotes ?? (complete ? (card.notes_preview ?? "") : "");
  const [notes, setNotes] = useState(initialNotes);
  const [replace, setReplace] = useState(false);
  const [applied, setApplied] = useState(dateInput(card.applied_at));
  const [error, setError] = useState<string | null>(null);
  const [confirmRemove, setConfirmRemove] = useState(false);

  const editableNotes = complete || replace;
  const notesChanged = editableNotes && notes !== initialNotes;
  const appliedChanged = applied !== dateInput(card.applied_at);
  const dirty = notesChanged || appliedChanged;
  const name =
    [card.title, card.company].filter(Boolean).join(" at ") || "Untitled job";

  function save() {
    setError(null);
    update.mutate(
      {
        card,
        notes: notesChanged ? (notes.trim() === "" ? null : notes) : undefined,
        applied_at: appliedChanged
          ? applied
            ? new Date(`${applied}T00:00:00`).toISOString()
            : null
          : undefined,
      },
      {
        onSuccess: () => {
          toast({ kind: "success", title: "Card saved" });
          onClose();
        },
        onError: (e) => setError(trackerErrorMessage(e)),
      },
    );
  }

  return (
    <Modal
      open
      onClose={onClose}
      variant="sheet"
      title={name}
      description="Move this application, set when you applied, and keep notes."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button
            variant="primary"
            disabled={!dirty}
            loading={update.isPending}
            onClick={save}
          >
            Save changes
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {card.score !== null && (
          <p className="text-body">
            <MetricChip>Match {card.score}</MetricChip>
          </p>
        )}
        <SelectField
          label="Stage"
          value={card.column}
          onChange={(e) => onMove(e.target.value as Column)}
        >
          {COLUMNS.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </SelectField>
        <InputField
          label="Applied on"
          type="date"
          value={applied}
          onChange={(e) => setApplied(e.target.value)}
        />
        {!complete && !replace && (
          <div className="rounded-control border border-border bg-surface-2 p-3">
            <p className="text-hint font-semibold text-muted">
              Current note (preview)
            </p>
            <p className="mt-1 text-body">{card.notes_preview}</p>
            <p className="mt-2 text-hint text-subtle">
              This note is longer than the preview and the full text can&apos;t
              be loaded here, so it can&apos;t be edited without replacing it.
            </p>
            <Button className="mt-2" size="sm" onClick={() => setReplace(true)}>
              Replace the note
            </Button>
          </div>
        )}
        {editableNotes && (
          <div>
            <TextareaField
              label={replace ? "New note (replaces the old one)" : "Notes"}
              value={notes}
              maxLength={NOTE_MAX}
              hint={
                complete && card.notes_preview
                  ? "Line breaks in older notes may appear as spaces."
                  : undefined
              }
              onChange={(e) => setNotes(e.target.value)}
            />
            {replace && (
              <Button
                className="mt-1"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setReplace(false);
                  setNotes(initialNotes);
                }}
              >
                Keep the old note
              </Button>
            )}
          </div>
        )}
        <div role="alert" aria-live="assertive">
          {error && <p className="font-medium text-bad">{error}</p>}
        </div>
        <div className="border-t border-border pt-3">
          {confirmRemove ? (
            <div className="flex flex-col gap-2">
              <p className="text-body">
                Remove this card from the tracker? The job itself is kept.
              </p>
              <div className="flex gap-2">
                <Button
                  variant="danger"
                  loading={remove.isPending}
                  onClick={() =>
                    remove.mutate(card.id, {
                      onSuccess: () => {
                        toast({
                          kind: "success",
                          title: "Removed from tracker",
                        });
                        onClose();
                      },
                      onError: (e) => setError(trackerErrorMessage(e)),
                    })
                  }
                >
                  Remove card
                </Button>
                <Button variant="ghost" onClick={() => setConfirmRemove(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              className="text-bad"
              onClick={() => setConfirmRemove(true)}
            >
              Remove from tracker
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
