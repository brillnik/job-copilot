import { cn } from "@/lib/cn";

type CheckboxProps = Omit<React.ComponentProps<"input">, "type"> & {
  label: React.ReactNode;
};

export function Checkbox({ label, className, ...props }: CheckboxProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-2.5 text-[13px] text-muted",
        className,
      )}
    >
      <input
        type="checkbox"
        className="mt-0.5 size-[18px] flex-none accent-accent"
        {...props}
      />
      <span>{label}</span>
    </label>
  );
}
