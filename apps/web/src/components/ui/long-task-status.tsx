"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";

const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/**
 * Progress for one request of unknown duration. There is no percentage and no
 * invented stages: just an honest label, the elapsed time (visual only, so
 * screen readers are not interrupted every second) and, once the wait gets
 * long, a second message that IS announced via the live region.
 */
export function LongTaskStatus({
  label,
  slowAfterSeconds = 30,
  slowMessage,
  action,
  className,
}: {
  label: string;
  slowAfterSeconds?: number;
  slowMessage?: string;
  /** e.g. a "Stop waiting" button. */
  action?: React.ReactNode;
  className?: string;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t0 = Date.now();
    const timer = setInterval(
      () => setElapsed(Math.floor((Date.now() - t0) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, []);
  const slow = slowMessage !== undefined && elapsed >= slowAfterSeconds;

  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-card border border-border bg-surface px-6 py-10 text-center",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="size-8 animate-spin rounded-full border-[3px] border-accent border-t-transparent motion-reduce:animate-none"
      />
      <div role="status" aria-live="polite" className="flex flex-col gap-1">
        <p className="text-section font-semibold">{label}</p>
        {slow && <p className="max-w-md text-muted">{slowMessage}</p>}
      </div>
      <p
        aria-hidden="true"
        className="font-mono text-hint text-subtle tabular-nums"
      >
        {mmss(elapsed)} elapsed
      </p>
      {action}
    </div>
  );
}
