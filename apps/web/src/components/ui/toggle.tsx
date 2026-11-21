"use client";

import { useId } from "react";
import { cn } from "@/lib/cn";

export function Toggle({
  checked,
  onCheckedChange,
  label,
  hint,
  disabled,
  className,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  hint?: string;
  disabled?: boolean;
  className?: string;
}) {
  const labelId = useId();
  return (
    <div
      className={cn(
        "flex min-h-11 items-center justify-between gap-4",
        className,
      )}
    >
      <span className="flex flex-col">
        <span id={labelId} className="text-body font-medium">
          {label}
        </span>
        {hint && <span className="text-hint text-subtle">{hint}</span>}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={labelId}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn(
          "relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
          checked
            ? "border-accent bg-accent"
            : "border-border-strong bg-surface-2",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "absolute size-5 rounded-full transition-transform",
            checked ? "translate-x-6 bg-on-accent" : "translate-x-1 bg-muted",
          )}
        />
        <span className="sr-only">{checked ? "On" : "Off"}</span>
      </button>
    </div>
  );
}
