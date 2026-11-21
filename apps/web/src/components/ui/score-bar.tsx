import { cn } from "@/lib/cn";

export type ScoreLevel = "ok" | "warn" | "bad";

/** ok >= 80, warn 60-79, bad < 60. */
export function scoreLevel(score: number): ScoreLevel {
  return score >= 80 ? "ok" : score >= 60 ? "warn" : "bad";
}

const text: Record<ScoreLevel, string> = {
  ok: "text-ok",
  warn: "text-warn",
  bad: "text-bad",
};
const fill: Record<ScoreLevel, string> = {
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
};
const word: Record<ScoreLevel, string> = {
  ok: "Strong match",
  warn: "Partial match",
  bad: "Weak match",
};

/** The number is always shown; colour only reinforces it. */
export function ScoreBar({
  score,
  label = "Match",
  className,
}: {
  score: number;
  label?: string;
  className?: string;
}) {
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const level = scoreLevel(value);
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <span
        className={cn(
          "w-9 text-right font-mono text-body font-semibold tabular-nums",
          text[level],
        )}
      >
        {value}
      </span>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-valuetext={`${value} out of 100, ${word[level].toLowerCase()}`}
        className="h-2 min-w-16 flex-1 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className={cn("h-full rounded-full", fill[level])}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}
