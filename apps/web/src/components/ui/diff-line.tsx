import { cn } from "@/lib/cn";

export type DiffSegment = { text: string; kind?: "same" | "ins" | "del" };

/**
 * One line of master vs tailored text. Insertions/deletions use <ins>/<del>,
 * a +/- gutter and underline/strike-through, so colour is never the only cue.
 */
export function DiffLine({
  side,
  segments,
  className,
}: {
  /** master = what is in the profile; tailored = what goes on the resume. */
  side: "master" | "tailored";
  segments: DiffSegment[];
  className?: string;
}) {
  const hasChange = segments.some((s) => s.kind && s.kind !== "same");
  const marker = !hasChange ? " " : side === "master" ? "-" : "+";
  return (
    <div
      className={cn(
        "flex gap-2 rounded-control px-2.5 py-1.5 text-body",
        hasChange
          ? side === "master"
            ? "bg-del text-del-text"
            : "bg-add text-add-text"
          : "bg-surface-2 text-text",
        className,
      )}
    >
      <span aria-hidden="true" className="w-3 shrink-0 font-mono select-none">
        {marker}
      </span>
      <span className="sr-only">
        {side === "master" ? "Master:" : "Tailored:"}
      </span>
      <p className="min-w-0">
        {segments.map((s, i) =>
          s.kind === "ins" ? (
            <ins
              key={i}
              className="font-semibold underline decoration-2 underline-offset-2"
            >
              {s.text}
            </ins>
          ) : s.kind === "del" ? (
            <del key={i} className="line-through decoration-2">
              {s.text}
            </del>
          ) : (
            <span key={i}>{s.text}</span>
          ),
        )}
      </p>
    </div>
  );
}
