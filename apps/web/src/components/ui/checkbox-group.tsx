import { cn } from "@/lib/cn";
import { Checkbox } from "./checkbox";

/** Multi-select as native checkboxes inside a fieldset (keyboard + screen-reader friendly). */
export function CheckboxGroup<T extends string>({
  legend,
  options,
  values,
  onChange,
  hint,
  error,
  className,
}: {
  legend: string;
  options: readonly T[];
  values: readonly T[];
  onChange: (values: T[]) => void;
  hint?: string;
  error?: string;
  className?: string;
}) {
  return (
    <fieldset className={cn("min-w-0", className)}>
      <legend className="mb-1.5 text-[13px] font-medium">{legend}</legend>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3 md:grid-cols-4">
        {options.map((o) => (
          <Checkbox
            key={o}
            label={o}
            checked={values.includes(o)}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? options.filter((x) => x === o || values.includes(x))
                  : values.filter((x) => x !== o),
              )
            }
            className="min-h-11 items-center text-body text-text md:min-h-8"
          />
        ))}
      </div>
      {(error || hint) && (
        <p
          role={error ? "alert" : undefined}
          className={cn("mt-1.5 text-hint", error ? "font-medium text-bad" : "text-subtle")}
        >
          {error ?? hint}
        </p>
      )}
    </fieldset>
  );
}
