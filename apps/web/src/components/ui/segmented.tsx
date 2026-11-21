"use client";

import { useId } from "react";
import { cn } from "@/lib/cn";

export type SegmentedOption<T extends string> = { value: T; label: string };

/** Radio-group semantics: arrow keys move + select, one tab stop (native radios). */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
  className,
}: {
  label: string;
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}) {
  const name = useId();
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn(
        "inline-flex rounded-control border border-border-strong bg-surface-2 p-0.5",
        className,
      )}
    >
      {options.map((o) => (
        <label
          key={o.value}
          className={cn(
            "relative inline-flex min-h-11 cursor-pointer items-center justify-center rounded-[6px] px-4 text-body font-medium md:min-h-8 md:px-3",
            "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus",
            value === o.value
              ? "bg-surface text-text shadow-sm ring-1 ring-border-strong"
              : "text-muted hover:text-text",
          )}
        >
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={value === o.value}
            onChange={() => onChange(o.value)}
            className="sr-only"
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}
