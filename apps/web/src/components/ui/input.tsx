import { cn } from "@/lib/cn";

export const controlClass =
  "w-full rounded-control border border-border-strong bg-surface px-3 text-body text-text " +
  "placeholder:text-subtle focus:border-focus focus:outline-2 focus:-outline-offset-1 focus:outline-focus " +
  "aria-invalid:border-bad disabled:cursor-not-allowed disabled:opacity-60";

export function Input({ className, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      className={cn(controlClass, "h-11 md:h-[38px]", className)}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: React.ComponentProps<"textarea">) {
  return (
    <textarea
      className={cn(controlClass, "min-h-24 py-2", className)}
      {...props}
    />
  );
}

export function Select({
  className,
  ...props
}: React.ComponentProps<"select">) {
  return (
    <select
      className={cn(controlClass, "h-11 md:h-[38px]", className)}
      {...props}
    />
  );
}
