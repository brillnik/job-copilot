"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusChip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { Modal } from "@/components/ui/modal";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { copyFor } from "@/features/common/error-copy";
import { formatDateTime } from "@/features/common/format";
import {
  type GmailStatus,
  type Suggestion,
  useConnectGmail,
  useDisconnectGmail,
  useGmailStatus,
  useResolveSuggestion,
  useSuggestions,
} from "./hooks";
import { SuggestionCard } from "./suggestion-card";

const ERRORS = {
  already_resolved:
    "That suggestion was already handled. The list has been refreshed.",
  gmail_not_configured: "Gmail connection isn't set up on this server yet.",
  feature_disabled: "Gmail reply tracking is switched off for your account.",
  not_found: "That suggestion no longer exists.",
};

export function GmailSection() {
  const status = useGmailStatus();
  // The feature is hidden entirely when the server says it is off for this user.
  if (status.isSuccess && !status.data.enabled) return null;

  return (
    <section aria-labelledby="gmail-h" className="space-y-3">
      <div>
        <h2 id="gmail-h" className="text-section font-semibold">
          Gmail reply tracking
        </h2>
        <p className="text-muted">
          Reads only email headers and a short snippet to spot replies from
          employers, then suggests moving the card on your tracker. Clear-cut
          replies may move a card on their own; the rest wait for your
          confirmation.
        </p>
      </div>
      {status.isPending ? (
        <SkeletonGroup label="Loading Gmail status">
          <Skeleton className="h-28 rounded-card" />
        </SkeletonGroup>
      ) : status.isError ? (
        <ErrorState
          title="Couldn't load Gmail status"
          message={copyFor(status.error, ERRORS)}
          onRetry={() => status.refetch()}
          retrying={status.isFetching}
        />
      ) : (
        <Connected status={status.data} />
      )}
    </section>
  );
}

function Connected({ status }: { status: GmailStatus }) {
  const connect = useConnectGmail();
  const disconnect = useDisconnectGmail();
  const { toast } = useToast();
  const [confirm, setConfirm] = useState(false);
  const [disconnectError, setDisconnectError] = useState<string>();

  function go() {
    connect.mutate(undefined, {
      // The consent screen is Google's; send the whole browser there.
      onSuccess: (url) => window.location.assign(url),
    });
  }

  if (!status.connected)
    return (
      <Card className="space-y-3">
        <p className="text-muted">Gmail is not connected.</p>
        <Button variant="primary" loading={connect.isPending} onClick={go}>
          Connect Gmail
        </Button>
        {connect.isError && (
          <p role="alert" className="text-hint font-medium text-bad">
            {copyFor(connect.error, ERRORS)}
          </p>
        )}
      </Card>
    );

  return (
    <div className="space-y-3">
      <Card className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip tone={status.needs_reconnect ? "warn" : "ok"}>
            {status.needs_reconnect ? "Needs reconnecting" : "Connected"}
          </StatusChip>
          <p className="text-hint text-subtle">
            {status.connected_at
              ? `Since ${formatDateTime(status.connected_at)}`
              : ""}
            {status.last_synced_at
              ? ` · last checked ${formatDateTime(status.last_synced_at)}`
              : ""}
          </p>
        </div>
        {status.needs_reconnect && (
          <p
            role="alert"
            className="rounded-control bg-warn-soft px-3 py-2 text-warn"
          >
            Google stopped accepting our access, so replies aren’t being
            tracked. Reconnect to resume.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {status.needs_reconnect && (
            <Button variant="primary" loading={connect.isPending} onClick={go}>
              Reconnect Gmail
            </Button>
          )}
          <Button
            variant="danger"
            onClick={() => {
              setDisconnectError(undefined);
              setConfirm(true);
            }}
          >
            Disconnect Gmail
          </Button>
        </div>
        {connect.isError && (
          <p role="alert" className="text-hint font-medium text-bad">
            {copyFor(connect.error, ERRORS)}
          </p>
        )}
      </Card>
      {!status.needs_reconnect && <Suggestions />}
      <Modal
        open={confirm}
        onClose={() => setConfirm(false)}
        title="Disconnect Gmail?"
        description="We revoke our access at Google and delete the connection and every email event we stored. Cards already on your tracker stay where they are."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(false)}>
              Keep it connected
            </Button>
            <Button
              variant="danger-solid"
              loading={disconnect.isPending}
              onClick={() =>
                disconnect.mutate(undefined, {
                  onSuccess: () => {
                    setConfirm(false);
                    toast({ kind: "success", title: "Gmail disconnected" });
                  },
                  onError: (e) => setDisconnectError(copyFor(e, ERRORS)),
                })
              }
            >
              Disconnect and delete
            </Button>
          </>
        }
      >
        {disconnectError && (
          <p role="alert" className="text-hint font-medium text-bad">
            {disconnectError}
          </p>
        )}
      </Modal>
    </div>
  );
}

function Suggestions() {
  const q = useSuggestions(true);
  const accept = useResolveSuggestion("accept");
  const dismiss = useResolveSuggestion("dismiss");
  const { toast } = useToast();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string>();

  if (q.isPending)
    return (
      <SkeletonGroup label="Loading suggestions">
        <Skeleton className="h-28 rounded-card" />
      </SkeletonGroup>
    );
  if (q.isError)
    return (
      <ErrorState
        title="Couldn't load suggestions"
        message={copyFor(q.error, ERRORS)}
        onRetry={() => q.refetch()}
        retrying={q.isFetching}
      />
    );
  const pending = q.data.filter((s) => s.status === "pending");

  function resolve(kind: "accept" | "dismiss", s: Suggestion) {
    setBusyId(s.id);
    setErrors((e) => ({ ...e, [s.id]: "" }));
    (kind === "accept" ? accept : dismiss).mutate(s.id, {
      onSuccess: () =>
        toast({
          kind: "success",
          title: kind === "accept" ? "Card moved" : "Suggestion dismissed",
        }),
      onError: (e) => setErrors((x) => ({ ...x, [s.id]: copyFor(e, ERRORS) })),
      onSettled: () => setBusyId(undefined),
    });
  }

  return (
    <div aria-live="polite" className="space-y-3">
      <h3 className="text-[15px] font-semibold">Suggestions</h3>
      {pending.length === 0 ? (
        <p className="text-muted">
          No suggestions waiting. We’ll show replies here when we spot them.
        </p>
      ) : (
        <ul className="space-y-3">
          {pending.map((s) => (
            <li key={s.id}>
              <SuggestionCard
                suggestion={s}
                busy={busyId === s.id}
                error={errors[s.id] || undefined}
                onConfirm={(x) => resolve("accept", x)}
                onDismiss={(x) => resolve("dismiss", x)}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
