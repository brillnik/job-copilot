import { cn } from "@/lib/cn";

export function Eyebrow({ className, ...props }: React.ComponentProps<"p">) {
  return (
    <p
      className={cn(
        "text-eyebrow font-semibold tracking-eyebrow text-subtle uppercase",
        className,
      )}
      {...props}
    />
  );
}
