"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Modal } from "@/components/ui/modal";
import { useState } from "react";

/** Shown when regenerating hits `red_flags`: the job has red flags the user must acknowledge. */
export function RedFlagConfirmDialog({
  open,
  flags,
  pending,
  onClose,
  onConfirm,
}: {
  open: boolean;
  flags: string[];
  pending?: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const [ack, setAck] = useState(false);
  return (
    <Modal
      open={open}
      onClose={onClose}
      variant="sheet"
      title="This job has red flags"
      description="Review them before generating another resume for it."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!ack}
            loading={pending}
            onClick={onConfirm}
          >
            Regenerate anyway
          </Button>
        </>
      }
    >
      {flags.length > 0 && (
        <ul className="mb-4 flex list-disc flex-col gap-1 pl-5">
          {flags.map((f) => (
            <li key={f}>{f}</li>
          ))}
        </ul>
      )}
      <Checkbox
        label="I've read the red flags and still want to continue."
        checked={ack}
        onChange={(e) => setAck(e.target.checked)}
        className="text-body text-text"
      />
    </Modal>
  );
}
