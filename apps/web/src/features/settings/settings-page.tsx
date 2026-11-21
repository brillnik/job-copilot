"use client";

import { PageHeader } from "@/components/shell/page-header";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { errorMessage } from "@/lib/api/errors";
import { useSettings } from "@/hooks/use-settings";
import { AccountSection } from "./account-section";
import { AppearanceSettings } from "./appearance-settings";
import { DevicesSection } from "./devices-section";
import { ExportSection } from "./export-section";
import { PreferencesForm } from "./preferences-form";

export function SettingsPage({
  autoOpenDelete = false,
}: {
  autoOpenDelete?: boolean;
}) {
  const q = useSettings();
  return (
    <>
      <PageHeader
        title="Settings"
        description="Preferences for how Job Copilot looks and behaves."
      />
      <div className="flex max-w-3xl flex-col gap-4">
        {q.isPending ? (
          <SkeletonGroup
            label="Loading settings"
            className="flex flex-col gap-4"
          >
            <Skeleton className="h-64 rounded-card" />
            <Skeleton className="h-40 rounded-card" />
          </SkeletonGroup>
        ) : q.isError ? (
          <ErrorState
            title="Couldn't load your preferences"
            message={errorMessage(q.error)}
            onRetry={() => void q.refetch()}
            retrying={q.isFetching}
          />
        ) : (
          // Keyed by revision of the *loaded* preferences only on first mount: later
          // revisions (e.g. a theme save) must not reset what the user is typing.
          <PreferencesForm settings={q.data} />
        )}
        <AppearanceSettings />
        <DevicesSection />
        <ExportSection />
        <AccountSection autoOpenDelete={autoOpenDelete} />
      </div>
    </>
  );
}
