"use client";

import { useFormContext } from "react-hook-form";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";

type TextFieldProps = Omit<
  React.ComponentProps<typeof Input>,
  "name" | "id" | "value" | "onChange" | "onBlur"
> & { name: string; label: string };

// Must be rendered inside <FormProvider> (see components/form/form.tsx).
export function TextField({ name, label, ...inputProps }: TextFieldProps) {
  const { register, formState } = useFormContext();
  const message = formState.errors[name]?.message as string | undefined;
  return (
    <div>
      <label htmlFor={name} className="mb-1.5 block text-[13px] font-medium">
        {label}
      </label>
      <Input
        id={name}
        aria-invalid={message ? true : undefined}
        {...register(name)}
        {...inputProps}
      />
      <FieldError message={message} />
    </div>
  );
}
