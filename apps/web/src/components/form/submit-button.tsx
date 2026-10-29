"use client";

import { useFormContext } from "react-hook-form";
import { Button, type ButtonProps } from "@/components/ui/button";

export function SubmitButton({
  disabled,
  ...props
}: Omit<ButtonProps, "type">) {
  const { formState } = useFormContext();
  return (
    <Button
      type="submit"
      disabled={disabled || formState.isSubmitting}
      {...props}
    />
  );
}
