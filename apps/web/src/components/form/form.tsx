"use client";

import {
  FormProvider,
  type FieldValues,
  type SubmitHandler,
  type UseFormReturn,
} from "react-hook-form";

// <Form> wires a useForm() instance to the field components in this folder.
//   const form = useForm({ resolver: zodResolver(schema), mode: "onTouched" });
//   <Form form={form} onSubmit={...}> <TextField name="email" .../> </Form>
export function Form<T extends FieldValues>({
  form,
  onSubmit,
  ...props
}: Omit<React.ComponentProps<"form">, "onSubmit"> & {
  form: UseFormReturn<T>;
  onSubmit: SubmitHandler<T>;
}) {
  return (
    <FormProvider {...form}>
      <form noValidate onSubmit={form.handleSubmit(onSubmit)} {...props} />
    </FormProvider>
  );
}
