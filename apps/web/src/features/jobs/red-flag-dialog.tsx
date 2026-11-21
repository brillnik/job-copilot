"use client";

import { Button } from "@/components/ui/button";
import { RedFlagChip } from "@/components/ui/chip";
import { Modal } from "@/components/ui/modal";

export function RedFlagDialog({
  open,
  flags,
  busy,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  flags: string[];
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onCancel}
      title="This posting has red flags"
      description="Check these before spending a tailoring run on it."
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" loading={busy} onClick={onConfirm}>
            Tailor anyway
          </Button>
        </>
      }
    >
      <ul className="flex flex-col gap-2">
        {flags.map((f) => (
          <li key={f}>
            <RedFlagChip className="h-auto py-1 whitespace-normal!">
              {f}
            </RedFlagChip>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
