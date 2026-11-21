import { cn } from "@/lib/cn";

export type ButtonVariant =
  "primary" | "secondary" | "ghost" | "danger" | "danger-solid";
export type ButtonSize = "sm" | "md" | "lg";

type Common = {
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  /** Shows a spinner, sets aria-busy and blocks clicks. */
  loading?: boolean;
};

// `iconOnly` buttons must be given an aria-label (enforced by a test and the
// jsx-a11y rules; the type stays a plain object so Omit<> keeps working).
export type ButtonProps = Common &
  React.ComponentProps<"button"> & {
    /** Square button with just an icon; requires aria-label. */
    iconOnly?: boolean;
  };

const variants: Record<ButtonVariant, string> = {
  primary:
    "border-accent bg-accent text-on-accent hover:enabled:border-accent-hover hover:enabled:bg-accent-hover",
  secondary:
    "border-border-strong bg-surface text-text hover:enabled:bg-surface-2",
  ghost:
    "border-transparent bg-transparent text-text hover:enabled:bg-surface-2",
  danger: "border-bad bg-surface text-bad hover:enabled:bg-bad-soft",
  "danger-solid": "border-bad bg-bad text-surface hover:enabled:opacity-90",
};

// >= 44px tall on mobile for every size; compact from md up for sm/md.
const sizes: Record<ButtonSize, string> = {
  sm: "min-h-11 px-3 text-[13px] md:min-h-8",
  md: "min-h-11 px-4 text-body md:min-h-10",
  lg: "min-h-12 px-5 text-[15px]",
};
const iconSizes: Record<ButtonSize, string> = {
  sm: "size-11 md:size-8",
  md: "size-11 md:size-10",
  lg: "size-12",
};

function Spinner() {
  return (
    <svg
      className="size-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" opacity=".25" />
      <path d="M21 12a9 9 0 0 0-9-9" strokeLinecap="round" />
    </svg>
  );
}

export function Button({
  variant = "secondary",
  size = "md",
  block,
  loading,
  iconOnly,
  className,
  type = "button",
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-control border font-medium whitespace-nowrap",
        "cursor-pointer transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        iconOnly ? iconSizes[size] : sizes[size],
        block && "w-full",
        className,
      )}
      {...props}
    >
      {loading && <Spinner />}
      {children}
      {loading && <span className="sr-only">Loading</span>}
    </button>
  );
}
