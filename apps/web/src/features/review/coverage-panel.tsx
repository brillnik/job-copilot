import { Card } from "@/components/ui/card";
import { CheckChip } from "@/components/ui/chip";
import { coveragePctLabel } from "./api";

/** Requirement coverage. The percentage is always printed; colour only reinforces it. */
export function CoveragePanel({
  covered,
  missing,
  pct,
}: {
  covered: string[];
  missing: string[];
  /** 0..1 */
  pct: number;
}) {
  const value = Math.round(Math.max(0, Math.min(1, pct)) * 100);
  return (
    <Card as="section" aria-labelledby="cov-h" className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 id="cov-h" className="text-section font-semibold">
          Requirement coverage
        </h2>
        <span className="font-mono text-section font-semibold tabular-nums">
          {coveragePctLabel(pct)}
        </span>
      </div>
      <div
        role="meter"
        aria-label="Requirement coverage"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-valuetext={`${value} percent of the must-have requirements are covered`}
        className="h-2 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className="h-full rounded-full bg-accent"
          style={{ width: `${value}%` }}
        />
      </div>
      <div>
        <h3 className="mb-1.5 text-hint font-semibold text-muted">
          Covered ({covered.length})
        </h3>
        {covered.length ? (
          <ul className="flex flex-wrap gap-1.5">
            {covered.map((c) => (
              <li key={c}>
                <CheckChip state="have">{c}</CheckChip>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-hint text-subtle">
            None of the requirements are covered yet.
          </p>
        )}
      </div>
      <div>
        <h3 className="mb-1.5 text-hint font-semibold text-muted">
          Missing ({missing.length})
        </h3>
        {missing.length ? (
          <ul className="flex flex-wrap gap-1.5">
            {missing.map((c) => (
              <li key={c}>
                <CheckChip state="missing">{c}</CheckChip>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-hint text-subtle">Nothing missing.</p>
        )}
      </div>
    </Card>
  );
}
