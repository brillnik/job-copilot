"use client";

import Link from "next/link";
import { useState } from "react";
import { Card } from "@/components/ui/card";
import { MetricChip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { InputField } from "@/components/ui/field";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { copyFor } from "@/features/common/error-copy";
import { reasonText } from "@/features/applications/status";
import { type DigestItem, useDigest } from "./hooks";

const ERRORS = { validation_error: "Pick a valid date." };

export function DigestView() {
  const [date, setDate] = useState<string>("");
  const q = useDigest(date || undefined);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <InputField
          label="Date"
          type="date"
          value={date || q.data?.date || ""}
          onChange={(e) => setDate(e.target.value)}
          className="w-full sm:w-56"
        />
        <Link
          href="/autopilot"
          className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2"
        >
          Autopilot settings
        </Link>
      </div>
      <div aria-live="polite">
        {q.isPending ? (
          <SkeletonGroup label="Loading the digest" className="space-y-3">
            <Skeleton className="h-24 rounded-card" />
            <Skeleton className="h-24 rounded-card" />
            <Skeleton className="h-24 rounded-card" />
          </SkeletonGroup>
        ) : q.isError ? (
          <ErrorState
            title="Couldn't load the digest"
            message={copyFor(q.error, ERRORS)}
            onRetry={() => q.refetch()}
            retrying={q.isFetching}
          />
        ) : (
          <div className="space-y-4">
            <Section
              title="Submitted"
              empty="Nothing was submitted on this day."
              items={q.data.submitted}
              kind="submitted"
            />
            <Section
              title="Needs a person"
              empty="Nothing is waiting for you."
              items={q.data.needs_a_person}
              kind="needs"
            />
            <Section
              title="Skipped"
              empty="Nothing was skipped."
              items={q.data.skipped}
              kind="skipped"
            />
          </div>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  empty,
  items,
  kind,
}: {
  title: string;
  empty: string;
  items: DigestItem[];
  kind: "submitted" | "needs" | "skipped";
}) {
  const id = `digest-${kind}`;
  return (
    <Card as="section" aria-labelledby={id}>
      <div className="flex items-center gap-2">
        <h2 id={id} className="text-section font-semibold">
          {title}
        </h2>
        <MetricChip>{items.length}</MetricChip>
      </div>
      {items.length === 0 ? (
        <p className="mt-2 text-muted">{empty}</p>
      ) : (
        <ul className="mt-3 divide-y divide-border">
          {items.map((it) => (
            <li
              key={it.application_id}
              className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 py-3 first:pt-0 last:pb-0"
            >
              <div className="min-w-0">
                <p className="font-medium">
                  {it.title ?? "Untitled role"}
                  {it.company ? (
                    <span className="text-muted"> · {it.company}</span>
                  ) : null}
                </p>
                {it.reason && (
                  <p className="text-muted">
                    {kind === "needs" ? "Waiting for: " : "Reason: "}
                    {reasonText(it.reason)}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <Link
                  href={`/applications/${encodeURIComponent(it.application_id)}`}
                  className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2 md:min-h-8"
                >
                  Details
                  <span className="sr-only">
                    {" "}
                    for {it.title ?? "this role"}
                  </span>
                </Link>
                {it.direct_link && (
                  <a
                    href={it.direct_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2 md:min-h-8"
                  >
                    Apply yourself
                    <span className="sr-only">
                      {" "}
                      for {it.title ?? "this role"} (opens in a new tab)
                    </span>
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
