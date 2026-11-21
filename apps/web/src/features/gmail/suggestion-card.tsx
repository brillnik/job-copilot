"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MetricChip } from "@/components/ui/chip";
import { humanize } from "@/features/common/format";
import type { Suggestion } from "./hooks";

const COLUMN: Record<Suggestion["suggested_column"], string> = {
  approved: "Approved",
  applied: "Applied",
  response: "Response",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
};

export function SuggestionCard({
  suggestion,
  onConfirm,
  onDismiss,
  busy,
  error,
}: {
  suggestion: Suggestion;
  onConfirm: (s: Suggestion) => void;
  onDismiss: (s: Suggestion) => void;
  busy?: boolean;
  error?: string;
}) {
  const who = suggestion.company ?? suggestion.title ?? "this job";
  const column = COLUMN[suggestion.suggested_column];
  return (
    <Card as="article" aria-label={`Move ${who} to ${column}`}>
      <h3 className="font-semibold">
        Move {who} to {column}?
      </h3>
      <p className="mt-1 text-muted">
        {suggestion.title && suggestion.company ? `${suggestion.title}. ` : ""}A
        recent email looks like:{" "}
        {humanize(suggestion.classification).toLowerCase()}.
      </p>
      <div className="mt-2">
        <MetricChip>{Math.round(suggestion.confidence * 100)}% sure</MetricChip>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          variant="primary"
          loading={busy}
          onClick={() => onConfirm(suggestion)}
        >
          Confirm
          <span className="sr-only">
            {" "}
            move {who} to {column}
          </span>
        </Button>
        <Button disabled={busy} onClick={() => onDismiss(suggestion)}>
          Dismiss<span className="sr-only"> suggestion for {who}</span>
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-2 text-hint font-medium text-bad">
          {error}
        </p>
      )}
    </Card>
  );
}
