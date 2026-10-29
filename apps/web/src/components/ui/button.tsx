import { cn } from "@/lib/cn";

type Variant = "default" | "primary";

export type ButtonProps = React.ComponentProps<"button"> & {
  variant?: Variant;
  block?: boolean;
};

const variants: Record<Variant, string> = {
  default:
    "border-border-strong bg-surface text-text hover:enabled:bg-surface-2",
  primary:
    "border-accent bg-accent text-on-accent hover:enabled:border-accent-hover hover:enabled:bg-accent-hover",
};

export function Button({
  variant = "default",
  block,
  className,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex h-11 items-center justify-center gap-2 whitespace-nowrap rounded-lg border px-4 text-[15px] font-medium",
        "cursor-pointer disabled:cursor-not-allowed disabled:opacity-45",
        variants[variant],
        block && "w-full",
        className,
      )}
      {...props}
    />
  );
}
