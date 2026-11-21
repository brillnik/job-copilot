"use client";

import { useId } from "react";
import { cn } from "@/lib/cn";
import { AlertIcon } from "./icons";
import { Input, Select, Textarea } from "./input";

type FieldChrome = {
  label: string;
  hint?: string;
  error?: string;
  /** Value was inferred with low confidence: asks the user to double-check (amber, with text). */
  lowConfidence?: boolean;
  /** Replaces the default low-confidence text, e.g. "Missing: no end date found.". */
  flagText?: string;
  className?: string;
};

type Ids = { id: string; describedBy?: string; invalid: boolean; low: boolean };

function FieldShell({
  label,
  hint,
  error,
  lowConfidence,
  flagText,
  className,
  ids,
  children,
}: FieldChrome & { ids: Ids; children: React.ReactNode }) {
  return (
    <div className={className}>
      <label htmlFor={ids.id} className="mb-1.5 block text-[13px] font-medium">
        {label}
      </label>
      {children}
      {hint && !error && (
        <p id={`${ids.id}-hint`} className="mt-1.5 text-hint text-subtle">
          {hint}
        </p>
      )}
      {lowConfidence && !error && (
        <p
          id={`${ids.id}-low`}
          className="mt-1.5 flex items-center gap-1.5 text-hint font-medium text-warn"
        >
          <AlertIcon className="size-3.5" />
          {flagText ?? "Low confidence: please check this value."}
        </p>
      )}
      {error && (
        <p
          id={`${ids.id}-err`}
          role="alert"
          className="mt-1.5 text-hint font-medium text-bad"
        >
          {error}
        </p>
      )}
    </div>
  );
}

function useIds(props: FieldChrome, given?: string): Ids {
  const auto = useId();
  const id = given ?? auto;
  const parts = [
    props.hint && !props.error ? `${id}-hint` : null,
    props.lowConfidence && !props.error ? `${id}-low` : null,
    props.error ? `${id}-err` : null,
  ].filter(Boolean);
  return {
    id,
    describedBy: parts.length ? parts.join(" ") : undefined,
    invalid: Boolean(props.error),
    low: Boolean(props.lowConfidence),
  };
}

const lowClass = "border-warn bg-warn-soft";

export function InputField({
  label,
  hint,
  error,
  lowConfidence,
  flagText,
  className,
  id,
  ...props
}: FieldChrome & Omit<React.ComponentProps<"input">, "className">) {
  const ids = useIds({ label, hint, error, lowConfidence }, id);
  return (
    <FieldShell {...{ label, hint, error, lowConfidence, flagText, className, ids }}>
      <Input
        id={ids.id}
        aria-invalid={ids.invalid || undefined}
        aria-describedby={ids.describedBy}
        className={ids.low && !ids.invalid ? lowClass : undefined}
        {...props}
      />
    </FieldShell>
  );
}

export function TextareaField({
  label,
  hint,
  error,
  lowConfidence,
  flagText,
  className,
  id,
  ...props
}: FieldChrome & Omit<React.ComponentProps<"textarea">, "className">) {
  const ids = useIds({ label, hint, error, lowConfidence }, id);
  return (
    <FieldShell {...{ label, hint, error, lowConfidence, flagText, className, ids }}>
      <Textarea
        id={ids.id}
        aria-invalid={ids.invalid || undefined}
        aria-describedby={ids.describedBy}
        className={cn(ids.low && !ids.invalid && lowClass)}
        {...props}
      />
    </FieldShell>
  );
}

export function SelectField({
  label,
  hint,
  error,
  lowConfidence,
  className,
  id,
  children,
  ...props
}: FieldChrome & Omit<React.ComponentProps<"select">, "className">) {
  const ids = useIds({ label, hint, error, lowConfidence }, id);
  return (
    <FieldShell {...{ label, hint, error, lowConfidence, className, ids }}>
      <Select
        id={ids.id}
        aria-invalid={ids.invalid || undefined}
        aria-describedby={ids.describedBy}
        className={cn(ids.low && !ids.invalid && lowClass)}
        {...props}
      >
        {children}
      </Select>
    </FieldShell>
  );
}
