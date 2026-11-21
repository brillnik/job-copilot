"use client";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusChip } from "@/components/ui/chip";
import { Segmented } from "@/components/ui/segmented";
import type { MaxPages } from "./api";

const OPTIONS = [
  { value: "1", label: "1 page" },
  { value: "2", label: "2 pages" },
  { value: "3", label: "3 pages" },
] as const;

const plural = (n: number) => `${n} ${n === 1 ? "page" : "pages"}`;

/** Page fit: label + one bar per page, plus the per-job length control. */
export function PageFit({
  count,
  lastPageFill,
  maxPages,
  length,
  onLengthChange,
  onRegenerate,
  regenerating,
  canRegenerate = true,
}: {
  count: number | null;
  /** 0..1 */
  lastPageFill: number;
  maxPages: number | null;
  length: MaxPages;
  onLengthChange: (n: MaxPages) => void;
  onRegenerate: () => void;
  regenerating?: boolean;
  canRegenerate?: boolean;
}) {
  const over = count !== null && maxPages !== null && count > maxPages;
  const total = Math.max(count ?? 0, maxPages ?? 0, 1);
  const fillPct = Math.round(Math.max(0, Math.min(1, lastPageFill)) * 100);
  return (
    <Card as="section" aria-labelledby="fit-h" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="fit-h" className="text-section font-semibold">
          Page fit
        </h2>
        {count === null ? (
          <StatusChip>Not measured yet</StatusChip>
        ) : over ? (
          <StatusChip tone="warn">
            Too long: {plural(count)}, limit {maxPages}
          </StatusChip>
        ) : (
          <StatusChip tone="ok">
            Fits: {plural(count)}
            {maxPages ? ` of ${maxPages}` : ""}
          </StatusChip>
        )}
      </div>
      {count !== null && (
        <>
          <ol
            aria-label="Page fill"
            className="flex list-none flex-col gap-1.5 p-0"
          >
            {Array.from({ length: total }, (_, i) => {
              const n = i + 1;
              const fill = n < count ? 100 : n === count ? fillPct : 0;
              const text =
                n > count ? "unused" : n < count ? "full" : `${fillPct}% full`;
              return (
                <li key={n} className="flex items-center gap-2.5">
                  <span className="w-14 shrink-0 text-hint text-muted">
                    Page {n}
                  </span>
                  <div
                    aria-hidden="true"
                    className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2"
                  >
                    <div
                      className={
                        over && n > (maxPages ?? total)
                          ? "h-full bg-warn"
                          : "h-full bg-accent"
                      }
                      style={{ width: `${fill}%` }}
                    />
                  </div>
                  <span className="w-16 shrink-0 text-right font-mono text-hint tabular-nums">
                    {text}
                  </span>
                </li>
              );
            })}
          </ol>
        </>
      )}
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        <Segmented<`${MaxPages}`>
          label="Resume length for this job"
          options={OPTIONS}
          value={`${length}`}
          onChange={(v) => onLengthChange(Number(v) as MaxPages)}
        />
        <Button
          loading={regenerating}
          disabled={!canRegenerate}
          onClick={onRegenerate}
        >
          Regenerate at {plural(length)}
        </Button>
      </div>
    </Card>
  );
}
