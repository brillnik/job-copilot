"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/cn";

/**
 * File picker + drag-and-drop target. The whole area is a <label> around a real
 * <input type="file">, so keyboard and screen-reader users get the native
 * control. Validation is the caller's job (pass the message as `error`).
 */
export function Dropzone({
  label,
  hint,
  accept,
  onFile,
  disabled,
  error,
  selected,
  className,
}: {
  label: string;
  hint?: string;
  accept?: string;
  onFile: (file: File) => void;
  disabled?: boolean;
  error?: string;
  /** Currently chosen file, shown inside the zone. */
  selected?: { name: string; detail?: string } | null;
  className?: string;
}) {
  const id = useId();
  const [over, setOver] = useState(false);
  const describedBy =
    [hint ? `${id}-hint` : null, error ? `${id}-err` : null]
      .filter(Boolean)
      .join(" ") || undefined;

  return (
    <div className={className}>
      <label
        htmlFor={id}
        onDragOver={(e) => {
          if (disabled) return;
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const f = e.dataTransfer.files?.[0];
          if (!disabled && f) onFile(f);
        }}
        className={cn(
          "flex min-h-44 cursor-pointer flex-col items-center justify-center gap-2 rounded-card border-2 border-dashed px-6 py-8 text-center",
          "has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-focus",
          over
            ? "border-accent bg-accent-soft"
            : "border-border-strong bg-surface",
          error && "border-bad",
          disabled && "cursor-not-allowed opacity-60",
        )}
      >
        <input
          id={id}
          type="file"
          accept={accept}
          disabled={disabled}
          aria-describedby={describedBy}
          aria-invalid={error ? true : undefined}
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onFile(f);
            e.target.value = ""; // allow choosing the same file again
          }}
        />
        <span className="text-section font-semibold">{label}</span>
        <span className="text-body text-muted">
          Drag a file here, or{" "}
          <span className="font-medium text-accent-text underline">
            choose a file
          </span>
        </span>
        {selected && (
          <span className="mt-1 inline-flex max-w-full items-center gap-2 rounded-control border border-border bg-surface-2 px-3 py-1.5 text-body">
            <span className="truncate font-medium">{selected.name}</span>
            {selected.detail && (
              <span className="font-mono text-hint text-subtle">
                {selected.detail}
              </span>
            )}
          </span>
        )}
      </label>
      {hint && (
        <p id={`${id}-hint`} className="mt-1.5 text-hint text-subtle">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={`${id}-err`}
          role="alert"
          className="mt-1.5 text-hint font-medium text-bad"
        >
          {error}
        </p>
      )}
    </div>
  );
}
