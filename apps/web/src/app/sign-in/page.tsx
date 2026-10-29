import type { Metadata } from "next";
import { SetupHeader } from "@/features/onboarding/setup-header";
import { SignInForm } from "@/features/sign-in/sign-in-form";

export const metadata: Metadata = {
  title: "Sign in · Job Copilot",
};

export default function SignInPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <SetupHeader current={0} />
      <main className="flex flex-1 justify-center px-4 pb-16 pt-10">
        <div className="flex w-full max-w-[440px] flex-col gap-6">
          <div className="flex flex-col gap-2">
            <p className="text-[11.5px] font-semibold uppercase tracking-[0.06em] text-subtle">
              Tailored in seconds, never fabricated
            </p>
            <h1 className="text-[28px] font-semibold leading-tight tracking-tight">
              Sign in to Job Copilot
            </h1>
            <p className="text-muted">
              Every line on a tailored resume traces back to your own profile.
              You approve every draft before it goes anywhere.
            </p>
          </div>
          <SignInForm />
        </div>
      </main>
    </div>
  );
}
