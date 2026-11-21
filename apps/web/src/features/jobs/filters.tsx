"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { InputField, SelectField } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { STATUS_LABEL } from "./format";
import type { JobFilters, JobStatus } from "./types";

export const DEFAULT_FILTERS: JobFilters = { sort: "created_at" };
const SCORES = [50, 60, 70, 80, 90];
const STATUSES = Object.keys(STATUS_LABEL) as JobStatus[];

export function hasActiveFilters(f: JobFilters) {
  return Boolean(f.status || f.min_score || f.city || f.q);
}

function useDebounced(value: string, onCommit: (v: string) => void) {
  const [local, setLocal] = useState(value);
  // Follow external resets (e.g. "Clear filters").
  const [seen, setSeen] = useState(value);
  if (value !== seen) {
    setSeen(value);
    setLocal(value);
  }
  useEffect(() => {
    if (local === value) return;
    const t = setTimeout(() => onCommit(local), 400);
    return () => clearTimeout(t);
  }, [local, value, onCommit]);
  return [local, setLocal] as const;
}

export function InboxFilters({
  filters,
  onChange,
}: {
  filters: JobFilters;
  onChange: (f: JobFilters) => void;
}) {
  const [city, setCity] = useDebounced(filters.city ?? "", (v) =>
    onChange({ ...filters, city: v.trim() || undefined }),
  );
  const [q, setQ] = useDebounced(filters.q ?? "", (v) =>
    onChange({ ...filters, q: v.trim() || undefined }),
  );
  return (
    <form
      role="search"
      aria-label="Filter jobs"
      onSubmit={(e) => e.preventDefault()}
      className="mb-4 flex flex-col gap-3"
    >
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <InputField
          label="Search"
          type="search"
          placeholder="Company or title"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="col-span-2 md:col-span-1"
        />
        <SelectField
          label="Minimum score"
          value={filters.min_score ?? ""}
          onChange={(e) =>
            onChange({
              ...filters,
              min_score: e.target.value ? Number(e.target.value) : undefined,
            })
          }
        >
          <option value="">Any score</option>
          {SCORES.map((s) => (
            <option key={s} value={s}>
              {s} and above
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Status"
          value={filters.status ?? ""}
          onChange={(e) =>
            onChange({
              ...filters,
              status: (e.target.value || undefined) as JobStatus | undefined,
            })
          }
        >
          <option value="">Active jobs</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </SelectField>
        <InputField
          label="City"
          placeholder="e.g. Bengaluru"
          value={city}
          onChange={(e) => setCity(e.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Segmented<JobFilters["sort"]>
          label="Sort by"
          options={[
            { value: "created_at", label: "Newest" },
            { value: "score", label: "Best match" },
          ]}
          value={filters.sort}
          onChange={(sort) => onChange({ ...filters, sort })}
        />
        {hasActiveFilters(filters) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange({ sort: filters.sort })}
          >
            Clear filters
          </Button>
        )}
      </div>
    </form>
  );
}
