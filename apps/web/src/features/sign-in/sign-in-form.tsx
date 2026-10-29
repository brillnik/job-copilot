"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";
import { CheckboxField } from "@/components/form/checkbox-field";
import { Form } from "@/components/form/form";
import { SubmitButton } from "@/components/form/submit-button";
import { TextField } from "@/components/form/text-field";
import { Button } from "@/components/ui/button";
import { GOOGLE_CONNECTION, login } from "./login";

const schema = z.object({
  email: z.string().trim().min(1, "Enter your email").email("Enter a valid email"),
  consent: z.boolean().refine((v) => v, "Tick the consent box to continue"),
});
type Values = z.infer<typeof schema>;

export function SignInForm() {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", consent: false },
    mode: "onTouched",
  });
  const consent = useWatch({ control: form.control, name: "consent" });

  return (
    <Form
      form={form}
      onSubmit={({ email }) => login({ login_hint: email })}
      className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-6"
    >
      <Button
        block
        disabled={!consent}
        onClick={() => login({ connection: GOOGLE_CONNECTION })}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 12h8M15 8.5" />
        </svg>
        Continue with Google
      </Button>

      <div className="flex items-center gap-3 text-[12.5px] text-subtle" aria-hidden="true">
        <span className="h-px flex-1 bg-border" />
        or with email
        <span className="h-px flex-1 bg-border" />
      </div>

      <TextField
        name="email"
        label="Work or personal email"
        type="email"
        autoComplete="email"
      />

      <SubmitButton block variant="primary" disabled={!consent}>
        Continue with email
      </SubmitButton>

      <CheckboxField
        name="consent"
        className="border-t border-border pt-2"
        label={
          <>
            I consent to Job Copilot storing my resume and profile data to
            tailor applications, as described in the privacy notice. I can
            export or delete it at any time, and withdraw consent in Settings.{" "}
            <span className="text-subtle">
              (Digital Personal Data Protection Act, 2023)
            </span>
          </>
        }
      />
      {!consent && (
        <p className="text-[12.5px] text-subtle" role="note">
          Tick the consent box to continue.
        </p>
      )}
    </Form>
  );
}
