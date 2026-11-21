import { cn } from "@/lib/cn";
import { CheckIcon, ClockIcon } from "./icons";

export type StepState = "done" | "running" | "waiting" | "queued";
export type Step = { label: string; state: StepState; detail?: string };

const stateText: Record<StepState, string> = {
  done: "Done",
  running: "Running",
  waiting: "Waiting for you",
  queued: "Queued",
};

function Marker({ state }: { state: StepState }) {
  const cls = "grid size-6 shrink-0 place-items-center rounded-full border";
  if (state === "done")
    return (
      <span className={cn(cls, "border-accent bg-accent text-on-accent")}>
        <CheckIcon className="size-3.5" />
      </span>
    );
  if (state === "running")
    return (
      <span
        className={cn(cls, "border-accent bg-accent-soft text-accent-text")}
      >
        <span className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
      </span>
    );
  if (state === "waiting")
    return (
      <span className={cn(cls, "border-accent bg-surface text-accent-text")}>
        <ClockIcon className="size-3.5" />
      </span>
    );
  return <span className={cn(cls, "border-border-strong bg-surface")} />;
}

/** Run progress. State is conveyed by icon AND text, never colour alone. */
export function Stepper({
  steps,
  label = "Progress",
}: {
  steps: Step[];
  label?: string;
}) {
  return (
    <ol aria-label={label} className="flex flex-col">
      {steps.map((s, i) => (
        <li
          key={s.label}
          aria-current={
            s.state === "running" || s.state === "waiting" ? "step" : undefined
          }
          className="relative flex gap-3 pb-4 last:pb-0"
        >
          {i < steps.length - 1 && (
            <span
              aria-hidden="true"
              className="absolute top-6 bottom-0 left-3 w-px -translate-x-1/2 bg-border"
            />
          )}
          <Marker state={s.state} />
          <div className="min-w-0">
            <p
              className={cn(
                "text-body font-medium",
                s.state === "queued" && "text-muted",
              )}
            >
              {s.label}
            </p>
            <p className="text-hint text-subtle">
              {stateText[s.state]}
              {s.detail ? ` · ${s.detail}` : ""}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
