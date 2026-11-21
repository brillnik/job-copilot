"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { copyFor } from "@/features/common/error-copy";
import { useApplyRun } from "./hooks";
import { APPLY_ERRORS } from "./status";

/** Manual apply for an approved run (POST /runs/{id}/apply), then on to the application. */
export function ApplyRun({ runId }: { runId: string }) {
  const apply = useApplyRun();
  const router = useRouter();
  return (
    <Card as="section" aria-labelledby="apply-h" className="max-w-xl space-y-3">
      <h2 id="apply-h" className="text-section font-semibold">
        Apply with your approved resume
      </h2>
      <p className="text-muted">
        We’ll fill in the employer’s form with the resume you approved and your
        saved answers. We never solve CAPTCHAs or sign in for you; if the site
        blocks us you get a direct link to finish yourself. You can cancel while
        it runs.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          loading={apply.isPending}
          onClick={() =>
            apply.mutate(runId, {
              onSuccess: (app) =>
                router.push(`/applications/${encodeURIComponent(app.id)}`),
            })
          }
        >
          Apply now
        </Button>
        <Link
          href="/applications"
          className="inline-flex min-h-11 items-center text-accent-text underline underline-offset-2"
        >
          All applications
        </Link>
      </div>
      <p role="status" aria-live="polite" className="sr-only">
        {apply.isPending ? "Starting the application" : ""}
      </p>
      {apply.isError && (
        <p role="alert" className="text-hint font-medium text-bad">
          {copyFor(apply.error, APPLY_ERRORS)}
        </p>
      )}
    </Card>
  );
}
