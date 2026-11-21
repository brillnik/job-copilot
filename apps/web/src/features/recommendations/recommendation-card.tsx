"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MetricChip, StatusChip } from "@/components/ui/chip";
import { ScoreBar } from "@/components/ui/score-bar";
import type { Recommendation } from "./hooks";

export function RecommendationCard({
  rec,
  onSave,
  onDismiss,
  saving,
  className,
}: {
  rec: Recommendation;
  onSave: (rec: Recommendation) => void;
  onDismiss: (rec: Recommendation) => void;
  saving?: boolean;
  className?: string;
}) {
  const saved = rec.action === "saved";
  const meta = [rec.company, rec.location].filter(Boolean).join(" · ");
  return (
    <Card as="article" aria-label={rec.title} className={className}>
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h2 className="text-section font-semibold">{rec.title}</h2>
          {meta && <p className="text-muted">{meta}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {rec.remote && <MetricChip>Remote</MetricChip>}
          {saved && <StatusChip tone="ok">Saved</StatusChip>}
        </div>
      </div>
      <ScoreBar
        score={rec.score}
        label={`Match score for ${rec.title}`}
        className="mt-3 max-w-sm"
      />
      {rec.reasons.length > 0 && (
        <>
          <h3 className="mt-4 text-[13px] font-medium">Why this was picked</h3>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-muted">
            {rec.reasons.map((r, i) => (
              <li key={`${i}-${r}`}>{r}</li>
            ))}
          </ul>
        </>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {saved ? (
          rec.job_id ? (
            <Link
              href={`/jobs/${encodeURIComponent(rec.job_id)}`}
              className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 font-medium text-on-accent hover:bg-accent-hover md:min-h-10"
            >
              Open saved job
            </Link>
          ) : null
        ) : (
          <>
            <Button
              variant="primary"
              loading={saving}
              onClick={() => onSave(rec)}
            >
              Save<span className="sr-only"> {rec.title}</span>
            </Button>
            <Button
              variant="secondary"
              disabled={saving}
              onClick={() => onDismiss(rec)}
            >
              Dismiss<span className="sr-only"> {rec.title}</span>
            </Button>
          </>
        )}
        <a
          href={rec.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex min-h-11 items-center px-2 text-accent-text underline underline-offset-2 md:min-h-10"
        >
          View posting
          <span className="sr-only"> for {rec.title} (opens in a new tab)</span>
        </a>
      </div>
    </Card>
  );
}
