"use client";

import { useReviewCount } from "@/hooks/use-review-count";
import { cn } from "@/lib/cn";

/** Count of runs waiting in review. Hidden while loading, on error, or at zero. */
export function ReviewBadge({ className }: { className?: string }) {
  const { data } = useReviewCount();
  if (!data || data.count === 0) return null;
  const text = `${data.count}${data.more ? "+" : ""}`;
  return (
    <span
      className={cn(
        "inline-flex min-w-5 items-center justify-center rounded-full bg-accent px-1.5 font-mono text-[11px] leading-5 font-semibold text-on-accent",
        className,
      )}
    >
      <span aria-hidden="true">{text}</span>
      <span className="sr-only">{text} awaiting review</span>
    </span>
  );
}
