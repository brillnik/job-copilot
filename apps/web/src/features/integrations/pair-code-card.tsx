"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

/** Seconds left until `expiresAt`, ticking once a second. */
export function useSecondsLeft(expiresAt: string | null, nowFn = Date.now) {
  const target = expiresAt ? new Date(expiresAt).getTime() : null;
  const [now, setNow] = useState(nowFn);
  useEffect(() => {
    if (target === null) return;
    const t = setInterval(() => setNow(nowFn()), 1000);
    return () => clearInterval(t);
  }, [target, nowFn]);
  return target === null ? null : Math.max(0, Math.ceil((target - now) / 1000));
}

export function formatClock(total: number) {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/**
 * The one-time pairing code: large, monospaced, with a countdown. The countdown
 * is visual only; screen readers get "copied" and "expired" through the live region.
 */
export function PairCodeCard({
  code,
  expiresAt,
  onRegenerate,
  regenerating,
  className,
}: {
  code: string;
  expiresAt: string;
  onRegenerate?: () => void;
  regenerating?: boolean;
  className?: string;
}) {
  const left = useSecondsLeft(expiresAt);
  const expired = left === 0;
  // The note belongs to one code, so a fresh code starts clean.
  const [noted, setNoted] = useState<{ code: string; text: string }>();
  const note = noted?.code === code ? noted.text : "";
  const setNote = (text: string) => setNoted({ code, text });

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setNote("Code copied.");
    } catch {
      setNote("Couldn't copy. Select the code and copy it by hand.");
    }
  }

  return (
    <div
      className={cn(
        "rounded-card border border-border bg-surface-2 p-4 md:p-5",
        className,
      )}
    >
      <p className="text-hint text-subtle">Your one-time pairing code</p>
      <p
        aria-label={`Pairing code ${code.split("").join(" ")}`}
        className={cn(
          "mt-1 font-mono text-[40px] leading-tight font-semibold tracking-[0.12em] break-all select-all",
          expired && "text-subtle line-through",
        )}
      >
        {code}
      </p>
      <p className="mt-1 text-muted">
        {expired ? (
          "This code has expired."
        ) : (
          <>
            Expires in{" "}
            <span className="font-mono tabular-nums">
              {left === null ? "" : formatClock(left)}
            </span>
          </>
        )}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="primary" disabled={expired} onClick={copy}>
          Copy code
        </Button>
        {onRegenerate && (
          <Button loading={regenerating} onClick={onRegenerate}>
            {expired ? "Get a new code" : "New code"}
          </Button>
        )}
      </div>
      <p role="status" aria-live="polite" className="mt-2 text-hint text-muted">
        {expired ? "Code expired. Get a new code to pair." : note}
      </p>
    </div>
  );
}
