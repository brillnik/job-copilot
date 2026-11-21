"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ErrorState } from "@/components/ui/error-state";
import { meKey, useMe } from "@/hooks/use-me";
import { api } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { unwrap } from "@/lib/api/unwrap";
import { clearConsentTick, hasConsentTick, POLICY_VERSION } from "@/lib/policy";
import { PageLoading } from "./setup-gate";

export const CONSENT_TEXT =
  "I consent to Job Copilot storing my resume and profile data to tailor applications, as described in the privacy notice. I can export or delete it at any time, and withdraw consent in Settings.";

/**
 * Records DPDP consent via POST /me/consent. If the box was already ticked on
 * the sign-in screen (carried across the Auth0 redirect), it is recorded
 * straight away; otherwise the user ticks it here. Nothing else is reachable
 * until a consent row exists.
 */
export function ConsentStep() {
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const [ticked, setTicked] = useState(false);
  const auto = useRef(false);

  const record = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/me/consent", { body: { policy_version: POLICY_VERSION } }),
      ),
    onSuccess: () => {
      clearConsentTick();
      return qc.invalidateQueries({ queryKey: meKey }).then(() => router.replace("/"));
    },
  });

  const alreadyConsented = !!me.data?.consent;
  useEffect(() => {
    if (me.data && alreadyConsented) router.replace("/");
  }, [me.data, alreadyConsented, router]);

  const carried = me.isSuccess && !alreadyConsented && hasConsentTick();
  useEffect(() => {
    if (carried && !auto.current) {
      auto.current = true;
      record.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [carried]);

  if (me.isPending || alreadyConsented) return <PageLoading />;

  const showForm = !carried || record.isError;
  return (
    <>
      <PageHeader
        level="screen"
        eyebrow="Before we start"
        title="Your data, your consent"
        description="Job Copilot needs your permission to store your resume and profile so it can tailor applications."
      />
      <div role="status" aria-live="polite" className="sr-only">
        {record.isPending ? "Recording your consent" : ""}
      </div>
      {!showForm ? (
        <p className="text-muted">Recording your consent…</p>
      ) : (
        <form
          className="flex flex-col gap-4 rounded-card border border-border bg-surface p-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (ticked) record.mutate();
          }}
        >
          <Checkbox
            label={CONSENT_TEXT}
            checked={ticked}
            onChange={(e) => setTicked(e.target.checked)}
          />
          {record.isError && (
            <ErrorState
              title="Couldn't record your consent"
              message={errorMessage(record.error)}
              onRetry={() => record.mutate()}
              retrying={record.isPending}
            />
          )}
          <div className="flex items-center gap-3">
            <Button
              type="submit"
              variant="primary"
              disabled={!ticked}
              loading={record.isPending}
            >
              Agree and continue
            </Button>
            {!ticked && (
              <span className="text-hint text-subtle">
                Tick the box to continue.
              </span>
            )}
          </div>
        </form>
      )}
    </>
  );
}
