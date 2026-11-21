"use client";

import { useMe } from "./use-me";
import { useApprovedProfile, useDraftProfile } from "./use-profile";
import { useSettings } from "./use-settings";
import { ONBOARDING_PATHS } from "@/features/onboarding/constants";

export type SetupStep = keyof typeof ONBOARDING_PATHS;

export type SetupStatus =
  | { state: "loading" }
  | { state: "error"; error: unknown; retry: () => void }
  | { state: "ready"; next: SetupStep | null };

/**
 * Where a signed-in user stands:
 *   consent -> (no approved profile) upload or review -> preferences -> done.
 * `next` is the first incomplete step, or null when setup is finished.
 */
export function useSetupStatus(): SetupStatus {
  const me = useMe();
  const consented = !!me.data?.consent;
  const approved = useApprovedProfile();
  const settings = useSettings();
  const needsDraft = approved.data === null;
  const draft = useDraftProfile(needsDraft);

  const failed = [me, approved, settings, needsDraft ? draft : null].find(
    (q) => q?.isError,
  );
  if (failed) {
    return {
      state: "error",
      error: failed.error,
      retry: () => {
        for (const q of [me, approved, settings, draft])
          if (q.isError) void q.refetch();
      },
    };
  }
  if (me.isPending) return { state: "loading" };
  if (!consented) return { state: "ready", next: "consent" };
  if (
    approved.isPending ||
    settings.isPending ||
    (needsDraft && draft.isPending)
  )
    return { state: "loading" };
  if (approved.data === null)
    return { state: "ready", next: draft.data ? "review" : "upload" };
  if (!settings.data?.configured)
    return { state: "ready", next: "preferences" };
  return { state: "ready", next: null };
}
