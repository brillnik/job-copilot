"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";
import { Chip } from "./chip";
import { XIcon } from "./icons";
import { Input } from "./input";

/** Free-text list (e.g. target roles): type + Enter or Add; each value is a removable chip. */
export function TagInput({
  label,
  values,
  onChange,
  max,
  maxLength = 80,
  hint,
  error,
  placeholder,
  addLabel = "Add",
  className,
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  max?: number;
  maxLength?: number;
  hint?: string;
  error?: string;
  placeholder?: string;
  addLabel?: string;
  className?: string;
}) {
  const id = useId();
  const [draft, setDraft] = useState("");
  const atMax = max !== undefined && values.length >= max;

  function add() {
    const v = draft.trim();
    if (!v || atMax) return;
    if (!values.some((x) => x.toLowerCase() === v.toLowerCase())) onChange([...values, v]);
    setDraft("");
  }

  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-[13px] font-medium">
        {label}
      </label>
      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          maxLength={maxLength}
          placeholder={placeholder}
          disabled={atMax}
          aria-invalid={error ? true : undefined}
          aria-describedby={`${id}-d`}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button onClick={add} disabled={atMax || draft.trim() === ""}>
          {addLabel}
          <span className="sr-only"> {label}</span>
        </Button>
      </div>
      {values.length > 0 && (
        <ul aria-label={label} className="m-0 mt-2 flex list-none flex-wrap gap-1.5 p-0">
          {values.map((v) => (
            <li key={v}>
              <Chip className="gap-0 pr-0 text-text">
                {v}
                <button
                  type="button"
                  aria-label={`Remove ${v}`}
                  onClick={() => onChange(values.filter((x) => x !== v))}
                  className={cn(
                    "ml-1 grid min-h-6 min-w-6 cursor-pointer place-items-center rounded-full text-muted hover:text-text",
                    "md:size-6",
                  )}
                >
                  <XIcon className="size-3" />
                </button>
              </Chip>
            </li>
          ))}
        </ul>
      )}
      <p id={`${id}-d`} className={cn("mt-1.5 text-hint", error ? "font-medium text-bad" : "text-subtle")} role={error ? "alert" : undefined}>
        {error ?? hint ?? (max ? `${values.length} of ${max}` : undefined)}
      </p>
    </div>
  );
}
