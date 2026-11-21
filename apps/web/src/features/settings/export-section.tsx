"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusChip } from "@/components/ui/chip";
import { errorMessage } from "@/lib/api/errors";
import { downloadHref, useExport, useRequestExport } from "./api";

export function ExportSection() {
  const [id, setId] = useState<string | null>(null);
  const request = useRequestExport();
  const exp = useExport(id);
  const status = exp.data?.status;
  const busy = request.isPending || status === "queued" || status === "running";

  const message = request.isError
    ? errorMessage(request.error)
    : exp.isError
      ? errorMessage(exp.error)
      : status === "queued"
        ? "Export queued…"
        : status === "running"
          ? "Preparing your export…"
          : status === "ready"
            ? "Your export is ready."
            : status === "failed"
              ? "The export failed. You can request it again."
              : status === "expired"
                ? "The export expired. Request a new one."
                : "";

  return (
    <Card as="section" aria-labelledby="exp-h" className="flex flex-col gap-3">
      <div>
        <h2 id="exp-h" className="text-section font-semibold">
          Export your data
        </h2>
        <p className="text-muted">
          Download an encrypted archive of your profile, resumes and
          applications.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          loading={busy}
          onClick={() =>
            request.mutate(undefined, { onSuccess: (r) => setId(r.export_id) })
          }
        >
          {status === "ready" || status === "failed" || status === "expired"
            ? "Request a new export"
            : "Request export"}
        </Button>
        {status === "ready" && exp.data?.download_url && (
          <a
            href={downloadHref(exp.data.download_url)}
            download
            className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 text-body font-medium text-on-accent hover:bg-accent-hover md:min-h-10"
          >
            Download export
          </a>
        )}
        {status && (
          <StatusChip
            tone={
              status === "ready"
                ? "ok"
                : status === "failed"
                  ? "bad"
                  : "neutral"
            }
          >
            {status}
          </StatusChip>
        )}
      </div>
      <p
        role="status"
        aria-live="polite"
        className={
          status === "failed" || request.isError
            ? "text-bad"
            : "text-hint text-muted"
        }
      >
        {message}
        {status === "ready" && exp.data?.expires_at
          ? ` The archive is kept until ${new Date(exp.data.expires_at).toLocaleDateString()}.`
          : ""}
      </p>
    </Card>
  );
}
