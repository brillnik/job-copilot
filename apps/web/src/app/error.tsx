"use client";

import { ErrorState } from "@/components/ui/error-state";

export default function Error({
  retry,
}: {
  error: unknown;
  retry: () => void;
}) {
  return (
    <main className="grid min-h-dvh place-items-center p-6">
      <ErrorState
        title="Something went wrong"
        message="We couldn't show this page. Try again."
        onRetry={() => retry()}
      />
    </main>
  );
}
