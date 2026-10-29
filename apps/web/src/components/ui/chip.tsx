import { cn } from "@/lib/cn";

export function Chip({
  current,
  className,
  ...props
}: React.ComponentProps<"span"> & { current?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center whitespace-nowrap rounded-full border px-[9px] text-[12.5px] font-medium",
        current
          ? "border-transparent bg-accent-soft text-accent-text"
          : "border-border bg-surface-2 text-muted",
        className,
      )}
      {...props}
    />
  );
}
