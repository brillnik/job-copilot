"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { Toggle } from "@/components/ui/toggle";
import { copyFor } from "@/features/common/error-copy";
import { formatDateTime } from "@/features/common/format";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";

// The API stores the policy version the user agreed to but does not serve the
// policy text. Same convention as onboarding consent: configurable, default "2026-01".
export const TRAINING_POLICY_VERSION =
  process.env.NEXT_PUBLIC_TRAINING_POLICY_VERSION ?? "2026-01";

const key = ["me", "training-consent"] as const;

export function TrainingConsent() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: key,
    queryFn: () => unwrap(api.GET("/me/training-consent")),
  });
  const save = useMutation({
    mutationFn: (enabled: boolean) =>
      unwrap(
        api.PUT("/me/training-consent", {
          body: { enabled, policy_version: TRAINING_POLICY_VERSION },
        }),
      ),
    onSuccess: (data) => qc.setQueryData(key, data),
  });
  const [announce, setAnnounce] = useState("");

  return (
    <section aria-labelledby="train-h" className="space-y-3">
      <h2 id="train-h" className="text-section font-semibold">
        Help improve Job Copilot
      </h2>
      {q.isPending ? (
        <SkeletonGroup label="Loading your choice">
          <Skeleton className="h-24 rounded-card" />
        </SkeletonGroup>
      ) : q.isError ? (
        <ErrorState
          title="Couldn't load this setting"
          message={copyFor(q.error)}
          onRetry={() => q.refetch()}
          retrying={q.isFetching}
        />
      ) : (
        <Card className="space-y-2">
          <Toggle
            label="Include my anonymised data in model-training snapshots"
            checked={q.data.enabled}
            disabled={save.isPending}
            onCheckedChange={(enabled) => {
              setAnnounce("");
              save.mutate(enabled, {
                onSuccess: () =>
                  setAnnounce(
                    enabled
                      ? "Training data sharing is on."
                      : "Training data sharing is off.",
                  ),
              });
            }}
          />
          <p className="text-muted">
            When this is on, anonymised copies of your data, with no names or
            contact details, may go into datasets used to improve our models. It
            is off by default.
          </p>
          <p className="text-muted">
            Turning it off excludes you from <strong>future</strong> snapshots
            only. Snapshots already written contain no identifiers and can’t be
            changed.
          </p>
          {q.data.at && (
            <p className="text-hint text-subtle">
              Last changed {formatDateTime(q.data.at)}
              {q.data.policy_version
                ? ` (policy ${q.data.policy_version})`
                : ""}
              .
            </p>
          )}
          <p role="status" aria-live="polite" className="text-hint text-muted">
            {save.isPending ? "Saving…" : announce}
          </p>
          {save.isError && (
            <p role="alert" className="text-hint font-medium text-bad">
              {copyFor(save.error)}
            </p>
          )}
        </Card>
      )}
    </section>
  );
}
