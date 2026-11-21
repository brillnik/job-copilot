"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { TextareaField } from "@/components/ui/field";

/**
 * Paste box for jobs whose posting could not be read (needs_paste | failed).
 * The typed text is kept on error so nothing is lost.
 */
export function PastePanel({
  reason,
  failed,
  onSubmit,
  idPrefix,
}: {
  reason?: string | null;
  failed?: boolean;
  /** Reject with an Error whose message is shown under the box. */
  onSubmit: (text: string) => Promise<void>;
  idPrefix: string;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) {
      setError("Paste the job description first.");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await onSubmit(text);
      setText("");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't submit the text.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <p className="text-muted">
        {failed
          ? "We couldn't read this posting."
          : "We couldn't read this posting automatically."}{" "}
        {reason ? <span className="text-text">{reason}. </span> : null}
        {failed
          ? "Paste the posting text to try again; there is no automatic retry."
          : "Paste the posting text instead."}
      </p>
      <TextareaField
        id={`${idPrefix}-paste`}
        label="Job description text"
        rows={5}
        maxLength={100000}
        value={text}
        onChange={(e) => setText(e.target.value)}
        error={error}
      />
      <div>
        <Button type="submit" variant="primary" size="sm" loading={busy}>
          {failed ? "Retry with this text" : "Submit text"}
        </Button>
      </div>
    </form>
  );
}
