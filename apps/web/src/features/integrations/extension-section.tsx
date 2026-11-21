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
  type DeviceToken,
  useCreatePairCode,
  useDevices,
  useRevokeDevice,
} from "./extension-hooks";
import { PairCodeCard } from "./pair-code-card";

const ERRORS = { not_found: "That device was already removed." };

export function ExtensionSection() {
  const devices = useDevices();
  const pair = useCreatePairCode();
  const revoke = useRevokeDevice();
  const { toast } = useToast();
  const [target, setTarget] = useState<DeviceToken | null>(null);
  const [revokeError, setRevokeError] = useState<string>();

  return (
    <section
      id="extension"
      aria-labelledby="ext-h"
      className="scroll-mt-4 space-y-3"
    >
      <div>
        <h2 id="ext-h" className="text-section font-semibold">
          Browser extension
        </h2>
        <p className="text-muted">
          The extension saves jobs from any page and applies on Wellfound,
          Naukri and Hiring Cafe from your own browser. Get a code here, then
          type it into the extension.
        </p>
      </div>
      <Card className="space-y-3">
        {pair.data ? (
          <PairCodeCard
            code={pair.data.code}
            expiresAt={pair.data.expires_at}
            onRegenerate={() => pair.mutate()}
            regenerating={pair.isPending}
          />
        ) : (
          <div>
            <Button
              variant="primary"
              loading={pair.isPending}
              onClick={() => pair.mutate()}
            >
              Get a pairing code
            </Button>
            <p className="mt-2 text-hint text-subtle">
              The code works once and expires after 10 minutes.
            </p>
          </div>
        )}
        {pair.isError && (
          <p role="alert" className="text-hint font-medium text-bad">
            {copyFor(pair.error)}
          </p>
        )}
      </Card>

      <h3 className="text-[15px] font-semibold">Paired devices</h3>
      {devices.isPending ? (
        <SkeletonGroup label="Loading devices">
          <Skeleton className="h-16 rounded-card" />
        </SkeletonGroup>
      ) : devices.isError ? (
        <ErrorState
          title="Couldn't load your devices"
          message={copyFor(devices.error)}
          onRetry={() => devices.refetch()}
          retrying={devices.isFetching}
        />
      ) : devices.data.length === 0 ? (
        <p className="text-muted">No devices are paired yet.</p>
      ) : (
        <ul className="space-y-2" aria-label="Paired devices">
          {devices.data.map((d) => (
            <li key={d.id}>
              <Card className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <div className="min-w-0">
                  <p className="font-medium">
                    {d.device_name ?? "Unnamed device"}
                  </p>
                  <p className="text-hint text-subtle">
                    Paired {formatDateTime(d.created_at)}
                    {d.last_used_at
                      ? ` · last used ${formatDateTime(d.last_used_at)}`
                      : " · never used"}
                  </p>
                </div>
                {d.revoked_at ? (
                  <StatusChip>
                    Revoked {formatDateTime(d.revoked_at)}
                  </StatusChip>
                ) : (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => {
                      setRevokeError(undefined);
                      setTarget(d);
                    }}
                  >
                    Revoke
                    <span className="sr-only">
                      {" "}
                      {d.device_name ?? "device"}
                    </span>
                  </Button>
                )}
              </Card>
            </li>
          ))}
        </ul>
      )}
      <Modal
        open={target !== null}
        onClose={() => setTarget(null)}
        title="Revoke this device?"
        description="The extension on it is signed out and has to be paired again."
        footer={
          <>
            <Button variant="ghost" onClick={() => setTarget(null)}>
              Keep it
            </Button>
            <Button
              variant="danger-solid"
              loading={revoke.isPending}
              onClick={() =>
                target &&
                revoke.mutate(target.id, {
                  onSuccess: () => {
                    toast({ kind: "success", title: "Device revoked" });
                    setTarget(null);
                  },
                  onError: (e) => setRevokeError(copyFor(e, ERRORS)),
                })
              }
            >
              Revoke device
            </Button>
          </>
        }
      >
        <p className="font-medium">{target?.device_name ?? "Unnamed device"}</p>
        {revokeError && (
          <p role="alert" className="mt-2 text-hint font-medium text-bad">
            {revokeError}
          </p>
        )}
      </Modal>
    </section>
  );
}
