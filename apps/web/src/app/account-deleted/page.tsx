import type { Metadata } from "next";

export const metadata: Metadata = { title: "Account deleted · Job Copilot" };

export default function Page() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-4 px-4 py-12">
      <h1 className="text-page font-semibold">Your account is being deleted</h1>
      <p className="text-muted">
        You&apos;ve been signed out. Your profile, resumes and applications will be erased within 24 hours.
        You don&apos;t need to do anything else.
      </p>
      <p>
        <a
          href="/sign-in"
          className="inline-flex min-h-11 items-center rounded-control border border-border-strong bg-surface px-4 text-body font-medium hover:bg-surface-2"
        >
          Back to sign-in
        </a>
      </p>
    </main>
  );
}
