"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/api/errors";
import { type DeviceToken, useDevices, useRevokeDevice } from "./api";

const fmt = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      })
    : "Never";

export function DeviceList({
  devices,
  onRevoke,
  revokingId,
}: {
  devices: DeviceToken[];
  onRevoke: (d: DeviceToken) => void;
  revokingId?: string | null;
}) {
  const active = devices.filter((d) => !d.revoked_at);
  if (active.length === 0)
    return <p className="text-muted">No browser extension is connected.</p>;
  return (
    <ul className="m-0 flex list-none flex-col divide-y divide-border p-0">
      {active.map((d) => {
        const name = d.device_name ?? "Unnamed device";
        return (
          <li
            key={d.id}
            className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
          >
            <div className="min-w-0">
              <p className="font-medium">{name}</p>
              <p className="text-hint text-subtle">
                Connected {fmt(d.created_at)} · Last used {fmt(d.last_used_at)}
              </p>
            </div>
            <Button
              variant="danger"
              size="sm"
              loading={revokingId === d.id}
              onClick={() => onRevoke(d)}
              aria-label={`Revoke ${name}`}
            >
              Revoke
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

export function DevicesSection() {
  const q = useDevices();
  const revoke = useRevokeDevice();
  const { toast } = useToast();
  const [msg, setMsg] = useState("");
  return (
    <Card as="section" aria-labelledby="dev-h" className="flex flex-col gap-3">
      <div>
        <h2 id="dev-h" className="text-section font-semibold">
          Connected extension devices
        </h2>
        <p className="text-muted">
          Browsers allowed to fill in applications for you. Revoke any you
          don&apos;t recognise.
        </p>
      </div>
      <p role="status" aria-live="polite" className="sr-only">
        {msg}
      </p>
      {q.isPending ? (
        <SkeletonGroup label="Loading devices">
          <Skeleton className="h-12" />
        </SkeletonGroup>
      ) : q.isError ? (
        <ErrorState
          title="Couldn't load devices"
          message={errorMessage(q.error)}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
          className="py-6"
        />
      ) : (
        <DeviceList
          devices={q.data}
          revokingId={revoke.isPending ? revoke.variables : null}
          onRevoke={(d) =>
            revoke.mutate(d.id, {
              onSuccess: () => {
                setMsg(`${d.device_name ?? "Device"} revoked.`);
                toast({ kind: "success", title: "Device revoked" });
              },
              onError: (e) =>
                toast({
                  kind: "error",
                  title: "Couldn't revoke the device",
                  description: errorMessage(e),
                }),
            })
          }
        />
      )}
    </Card>
  );
}
