import { Card } from "@/components/ui/card";
import { CheckChip, RedFlagChip } from "@/components/ui/chip";
import type { Violation } from "./api";

const CODE_LABEL: Record<string, string> = {
  invented_number: "Invented number",
  unsupported_skill: "Unsupported skill",
  unknown_source: "Unknown source bullet",
};
export const codeLabel = (code: string) =>
  CODE_LABEL[code] ?? code.replaceAll("_", " ");

/** Fact-check result: pass/fail is always stated in words, flagged adds a flag icon. */
export function FactCheckPanel({
  violations,
  flagged,
  refused = [],
}: {
  violations: Violation[];
  flagged: boolean;
  /** Edits the server refused on the last save (not stored). */
  refused?: Violation[];
}) {
  const clean = violations.length === 0;
  return (
    <Card as="section" aria-labelledby="fc-h" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="fc-h" className="text-section font-semibold">
          Fact check
        </h2>
        {clean ? (
          <CheckChip state="have">
            Passed: every claim traces to your profile
          </CheckChip>
        ) : (
          <CheckChip state="missing">
            {violations.length} {violations.length === 1 ? "issue" : "issues"}{" "}
            remaining
          </CheckChip>
        )}
      </div>
      {flagged && (
        <p className="flex flex-wrap items-center gap-2 text-body">
          <RedFlagChip>Flagged for your attention</RedFlagChip>
          <span className="text-muted">
            Check the issues, coverage and page fit below before approving.
          </span>
        </p>
      )}
      {refused.length > 0 && (
        <div
          role="alert"
          className="rounded-control border border-bad bg-bad-soft p-3"
        >
          <p className="text-body font-semibold text-bad">
            {refused.length} {refused.length === 1 ? "edit was" : "edits were"}{" "}
            refused and not saved
          </p>
          <ul className="mt-1 flex list-disc flex-col gap-1 pl-5 text-hint">
            {refused.map((v, i) => (
              <li key={`${v.code}-${i}`}>
                <span className="font-medium">{codeLabel(v.code)}</span>
                {v.source_id ? ` (${v.source_id})` : ""}: {v.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!clean && (
        <ul className="flex flex-col gap-2">
          {violations.map((v, i) => (
            <li
              key={`${v.code}-${v.source_id ?? v.field}-${i}`}
              className="rounded-control border border-border bg-surface-2 p-2.5 text-body"
            >
              <p className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{codeLabel(v.code)}</span>
                <span className="font-mono text-hint text-subtle">
                  {v.source_id ?? v.field}
                </span>
              </p>
              <p className="text-muted">
                {v.message}
                {v.term ? <> (“{v.term}”)</> : null}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
