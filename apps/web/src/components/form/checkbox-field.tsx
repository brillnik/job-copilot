"use client";

import { useFormContext } from "react-hook-form";
import { Checkbox } from "@/components/ui/checkbox";
import { FieldError } from "@/components/ui/field-error";

export function CheckboxField({
  name,
  label,
  className,
}: {
  name: string;
  label: React.ReactNode;
  className?: string;
}) {
  const { register, formState } = useFormContext();
  const message = formState.errors[name]?.message as string | undefined;
  return (
    <div className={className}>
      <Checkbox label={label} {...register(name)} />
      <FieldError message={message} />
    </div>
  );
}
