"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useSetupStatus } from "@/hooks/use-setup-status";
import { errorMessage } from "@/lib/api/errors";
import { ONBOARDING_PATHS } from "./constants";

export function PageLoading({ label = "Loading" }: { label?: string }) {
  return (
    <SkeletonGroup label={label} className="mx-auto flex w-full max-w-[720px] flex-col gap-4 p-6">
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-40 w-full" />
      <Skeleton className="h-40 w-full" />
    </SkeletonGroup>
  );
}

/**
 * Guards the signed-in app: a user who has not finished setup is sent to the
 * first incomplete step (consent, upload/review, preferences) before anything else.
 */
export function SetupGate({ children }: { children: React.ReactNode }) {
  const status = useSetupStatus();
  const router = useRouter();
  const next = status.state === "ready" ? status.next : null;

  useEffect(() => {
    if (next) router.replace(ONBOARDING_PATHS[next]);
  }, [next, router]);

  if (status.state === "error") {
    return (
      <div className="mx-auto max-w-xl p-6">
        <ErrorState
          title="Couldn't load your account"
          message={errorMessage(status.error)}
          onRetry={status.retry}
        />
      </div>
    );
  }
  if (status.state === "loading") return <PageLoading label="Loading your account" />;
  if (next) return <PageLoading label="Taking you to setup" />;
  return <>{children}</>;
}
