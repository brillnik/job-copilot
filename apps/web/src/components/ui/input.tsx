import { cn } from "@/lib/cn";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-[38px] w-full rounded-lg border border-border-strong bg-surface px-3 text-sm text-text",
        "placeholder:text-subtle focus:border-focus focus:outline-2 focus:-outline-offset-1 focus:outline-focus",
        "aria-invalid:border-bad",
        className,
      )}
      {...props}
    />
  );
}
