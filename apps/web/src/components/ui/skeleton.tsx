import { cn } from "@/lib/cn";

/** Placeholder block. Wrap groups in <SkeletonGroup> for the live-region label. */
export function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-control bg-surface-2", className)}
      {...props}
    />
  );
}

export function SkeletonGroup({
  label = "Loading",
  children,
  className,
}: {
  label?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={className}
    >
      <span className="sr-only">{label}…</span>
      {children}
    </div>
  );
}
