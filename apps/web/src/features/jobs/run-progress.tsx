"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Stepper } from "@/components/ui/stepper";
import { useEventStream } from "@/hooks/use-event-stream";
import { runKey } from "./hooks";
import {
  buildRunSteps,
  emptyProgress,
  reduceStep,
  type StepProgress,
} from "./run-steps";
import type { RunStatus } from "./types";

// in_review is not terminal for the backend stream (it keeps sending
// heartbeats), so the client closes its own subscription there.
const STOP: readonly string[] = [
  "in_review",
  "approved",
  "rejected",
  "needs_attention",
  "cancelled",
];

type Msg = { type?: string; payload?: Record<string, unknown> };

/** Live stepper for one active run, fed by GET /runs/{id}/events (SSE). */
export function RunProgress({
  runId,
  status,
  currentStep,
}: {
  runId: string;
  status: RunStatus;
  currentStep: string | null;
}) {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<StepProgress>(emptyProgress);
  const [announce, setAnnounce] = useState("");
  const active = !STOP.includes(status);

  const stream = useEventStream({
    url: active ? `/api/runs/${runId}/events` : null,
    isTerminal: (m) =>
      (m.data as Msg).type === "status" &&
      STOP.includes(String((m.data as Msg).payload?.status)),
    onMessage: (m) => {
      const d = m.data as Msg;
      if (d.type === "step" && typeof d.payload?.step === "string") {
        const step = d.payload.step;
        const it = d.payload.iteration;
        setProgress((p) =>
          reduceStep(p, step, typeof it === "number" ? it : undefined),
        );
      } else if (d.type === "status") {
        setAnnounce(
          `Run status: ${String(d.payload?.status).replace(/_/g, " ")}`,
        );
        void qc.invalidateQueries({ queryKey: runKey(runId) });
        void qc.invalidateQueries({ queryKey: ["jobs"] });
      }
    },
  });

  return (
    <div>
      <Stepper
        label="Tailoring progress"
        steps={buildRunSteps(status, progress, currentStep)}
      />
      <p role="status" aria-live="polite" className="sr-only">
        {announce}
      </p>
      {active && stream === "reconnecting" && (
        <p className="mt-2 text-hint text-subtle">
          Reconnecting to live progress…
        </p>
      )}
    </div>
  );
}
