import { cn } from "@/lib/cn";
import { CheckIcon, ClockIcon, FlagIcon, QuestionIcon, XIcon } from "./icons";

const base =
  "inline-flex min-h-6 items-center gap-1 rounded-full border px-[9px] text-hint font-medium whitespace-nowrap";

/** Neutral chip; `current` highlights the active step (used by the setup header). */
export function Chip({
  current,
  className,
  ...props
}: React.ComponentProps<"span"> & { current?: boolean }) {
  return (
    <span
      className={cn(
        base,
        current
          ? "border-transparent bg-accent-soft text-accent-text"
          : "border-border bg-surface-2 text-muted",
        className,
      )}
      {...props}
    />
  );
}

export function SkillChip({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      className={cn(base, "border-border bg-surface-2 text-text", className)}
      {...props}
    />
  );
}

/** Numbers, CTC, counts: JetBrains Mono. */
export function MetricChip({
  className,
  ...props
}: React.ComponentProps<"span">) {
  return (
    <span
      className={cn(
        base,
        "border-border bg-surface font-mono text-text tabular-nums",
        className,
      )}
      {...props}
    />
  );
}

/**
 * A claim's provenance, e.g. "§exp.2.b3". Focusable; the original text from the
 * profile shows in a tooltip on hover AND keyboard focus.
 */
export function SourceChip({
  id,
  original,
  label,
  className,
}: {
  id: string;
  original: string;
  /** Shown on the chip instead of the full id (long ids are shortened by callers). */
  label?: string;
  className?: string;
}) {
  const tipId = `tip-${id.replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  return (
    <span className="group relative inline-flex">
      <button
        type="button"
        aria-describedby={tipId}
        className={cn(
          base,
          "cursor-help border-border-strong bg-surface font-mono text-accent-text",
          className,
        )}
      >
        {label ?? id}
      </button>
      <span
        id={tipId}
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-full left-0 z-30 mb-1.5 w-max max-w-[min(20rem,80vw)] rounded-control border border-border-strong bg-surface px-3 py-2 text-hint font-normal whitespace-normal text-text opacity-0 shadow-lg transition-opacity group-focus-within:visible group-focus-within:opacity-100 group-hover:visible group-hover:opacity-100"
      >
        <span className="mb-0.5 block text-eyebrow font-semibold tracking-eyebrow text-subtle uppercase">
          Original text
        </span>
        {original}
      </span>
    </span>
  );
}

export type StatusTone = "neutral" | "accent" | "ok" | "warn" | "bad";
const tones: Record<StatusTone, string> = {
  neutral: "border-border bg-surface-2 text-muted",
  accent: "border-transparent bg-accent-soft text-accent-text",
  ok: "border-transparent bg-ok-soft text-ok",
  warn: "border-transparent bg-warn-soft text-warn",
  bad: "border-transparent bg-bad-soft text-bad",
};

/** Pipeline status ("In review", "Applied"). Always text; tone is decoration. */
export function StatusChip({
  tone = "neutral",
  className,
  ...props
}: React.ComponentProps<"span"> & { tone?: StatusTone }) {
  return <span className={cn(base, tones[tone], className)} {...props} />;
}

export type CheckState = "have" | "ask" | "missing";
const checks: Record<
  CheckState,
  { cls: string; label: string; Icon: typeof CheckIcon }
> = {
  have: { cls: "bg-ok-soft text-ok", label: "Have", Icon: CheckIcon },
  ask: { cls: "bg-warn-soft text-warn", label: "Ask", Icon: QuestionIcon },
  missing: { cls: "bg-bad-soft text-bad", label: "Missing", Icon: XIcon },
};

/** Fact-check / requirement coverage: icon + word + colour. */
export function CheckChip({
  state,
  children,
  className,
}: {
  state: CheckState;
  children: React.ReactNode;
  className?: string;
}) {
  const { cls, label, Icon } = checks[state];
  return (
    <span className={cn(base, "border-transparent", cls, className)}>
      <Icon className="size-3.5" />
      <span className="sr-only">{label}: </span>
      {children}
    </span>
  );
}

export function RedFlagChip({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(base, "border-transparent bg-bad-soft text-bad", className)}
    >
      <FlagIcon className="size-3.5" />
      <span className="sr-only">Red flag: </span>
      {children}
    </span>
  );
}

export function ComingSoonChip({
  children = "Coming soon",
  className,
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        base,
        "border-dashed border-border-strong bg-transparent text-subtle",
        className,
      )}
    >
      <ClockIcon className="size-3.5" />
      {children}
    </span>
  );
}
