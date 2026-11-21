"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { ErrorState } from "@/components/ui/error-state";
import { useMe } from "@/hooks/use-me";
import { errorMessage } from "@/lib/api/errors";
import { ONBOARDING_PATHS } from "./constants";
import { PageLoading } from "./setup-gate";
import { SetupHeader } from "./setup-header";

const STEP_BY_PATH: Record<string, number> = {
  [ONBOARDING_PATHS.consent]: 0,
  [ONBOARDING_PATHS.upload]: 1,
  [ONBOARDING_PATHS.review]: 2,
  [ONBOARDING_PATHS.preferences]: 3,
};

/** Shared chrome for /onboarding/*. Everything but the consent step needs consent first. */
export function OnboardingFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const me = useMe();
  const onConsent = pathname === ONBOARDING_PATHS.consent;
  const consented = !!me.data?.consent;
  const mustConsent = me.isSuccess && !consented && !onConsent;

  useEffect(() => {
    if (mustConsent) router.replace(ONBOARDING_PATHS.consent);
  }, [mustConsent, router]);

  return (
    <div className="flex min-h-dvh flex-col">
      <SetupHeader current={STEP_BY_PATH[pathname] ?? 0} />
      <main id="main" className="flex flex-1 justify-center px-4 pt-8 pb-16 sm:pt-10">
        <div className="w-full max-w-[720px]">
          {me.isError ? (
            <ErrorState
              title="Couldn't load your account"
              message={errorMessage(me.error)}
              onRetry={() => void me.refetch()}
              retrying={me.isFetching}
            />
          ) : me.isPending || mustConsent ? (
            <PageLoading />
          ) : (
            children
          )}
        </div>
      </main>
    </div>
  );
}
