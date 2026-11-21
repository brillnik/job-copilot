"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Modal } from "@/components/ui/modal";
import { SparkIcon } from "@/components/ui/icons";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { TextareaField } from "@/components/ui/field";
import { useToast } from "@/components/ui/toast";
import { copyFor } from "@/features/common/error-copy";
import {
  type Recommendation,
  useDismissRecommendation,
  useRecommendations,
  useSaveRecommendation,
} from "./hooks";
import { RecommendationCard } from "./recommendation-card";

const SAVE_ERRORS = {
  not_found: "This posting is no longer available.",
};
const DISMISS_ERRORS = {
  invalid_state: "You already saved this one, so it can't be dismissed.",
};

export function ForYou() {
  const q = useRecommendations();
  const save = useSaveRecommendation();
  const dismiss = useDismissRecommendation();
  const { toast } = useToast();
  const [target, setTarget] = useState<Recommendation | null>(null);
  const [reason, setReason] = useState("");
  const [dismissError, setDismissError] = useState<string>();
  const [savingId, setSavingId] = useState<string>();

  if (q.isPending)
    return (
      <SkeletonGroup
        label="Loading today's recommendations"
        className="space-y-3"
      >
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-44 rounded-card" />
        ))}
      </SkeletonGroup>
    );
  if (q.isError)
    return (
      <ErrorState
        title="Couldn't load today's recommendations"
        message={copyFor(q.error)}
        onRetry={() => q.refetch()}
        retrying={q.isFetching}
      />
    );
  if (q.data.length === 0)
    return (
      <EmptyState
        icon={<SparkIcon className="size-6" />}
        title="Nothing new for you today"
        description="We pick roles from your profile and preferences each day. Check back later, or widen your target roles and cities."
        action={
          <Link
            href="/profile"
            className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2"
          >
            Review your profile
          </Link>
        }
      />
    );

  function onSave(rec: Recommendation) {
    setSavingId(rec.id);
    save.mutate(rec.id, {
      onSuccess: () => toast({ kind: "success", title: "Saved to your jobs" }),
      onError: (e) =>
        toast({
          kind: "error",
          title: "Couldn't save",
          description: copyFor(e, SAVE_ERRORS),
        }),
      onSettled: () => setSavingId(undefined),
    });
  }

  function close() {
    setTarget(null);
    setReason("");
    setDismissError(undefined);
  }

  function confirmDismiss() {
    if (!target) return;
    dismiss.mutate(
      { id: target.id, reason },
      {
        onSuccess: () => {
          toast({
            kind: "info",
            title: "Dismissed",
            description: "It won't show up again today.",
          });
          close();
        },
        // Keep the dialog (and the typed reason) open on failure.
        onError: (e) => setDismissError(copyFor(e, DISMISS_ERRORS)),
      },
    );
  }

  return (
    <>
      <ul className="space-y-3" aria-label="Today's recommendations">
        {q.data.map((rec) => (
          <li key={rec.id}>
            <RecommendationCard
              rec={rec}
              saving={savingId === rec.id}
              onSave={onSave}
              onDismiss={setTarget}
            />
          </li>
        ))}
      </ul>
      <Modal
        open={target !== null}
        onClose={close}
        title="Dismiss this role?"
        description={
          target
            ? `${target.title}${target.company ? ` at ${target.company}` : ""}`
            : undefined
        }
        variant="sheet"
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={dismiss.isPending}
              onClick={confirmDismiss}
            >
              Dismiss role
            </Button>
          </>
        }
      >
        <TextareaField
          label="Reason (optional)"
          hint="Helps us pick better roles. Up to 200 characters."
          maxLength={200}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          error={dismissError}
        />
      </Modal>
    </>
  );
}
