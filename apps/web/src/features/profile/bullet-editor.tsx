"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { TextareaField } from "@/components/ui/field";
import { errorMessage } from "@/lib/api/errors";
import { fieldErrors } from "@/lib/api/field-errors";

/**
 * Inline editor for one bullet. `onSave` should reject on failure; the text
 * stays in the box and the error shows next to it (422 messages from the API
 * go on the field, anything else as a message under it).
 */
export function BulletEditor({
  label,
  initial = "",
  onSave,
  onCancel,
}: {
  label: string;
  initial?: string;
  onSave: (text: string) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [text, setText] = useState(initial);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function save() {
    const t = text.trim();
    if (!t) return setError("Write the achievement before saving");
    if (t.length > 1000) return setError("Keep it under 1000 characters");
    setError(undefined);
    setBusy(true);
    try {
      await onSave(t);
    } catch (e) {
      setError(Object.values(fieldErrors(e))[0] ?? errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <TextareaField
        label={label}
        value={text}
        error={error}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="flex gap-2">
        <Button variant="primary" size="sm" loading={busy} onClick={save}>
          Save
        </Button>
        <Button size="sm" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
