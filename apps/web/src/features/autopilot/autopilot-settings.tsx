"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { StatusChip } from "@/components/ui/chip";
import { ErrorState } from "@/components/ui/error-state";
import { InputField } from "@/components/ui/field";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { copyFor } from "@/features/common/error-copy";
import { formatDate } from "@/features/common/format";
import { type Autopilot, useAutopilot, useSaveAutopilot } from "./hooks";
import {
  AUTOPILOT_ACK_TEXT,
  AUTOPILOT_WHAT_IT_DOES,
  SITE_KEYS,
  SITE_POLICY,
  type SiteKey,
} from "./policy";

const ERRORS = {
  acknowledgement_required:
    "The policy was updated. Reload this page, read it again and re-confirm.",
  validation_error: "One of the values is out of range. Check them and retry.",
};

export function AutopilotSettings() {
  const q = useAutopilot();
  if (q.isPending)
    return (
      <SkeletonGroup label="Loading autopilot settings" className="space-y-4">
        <Skeleton className="h-48 rounded-card" />
        <Skeleton className="h-56 rounded-card" />
      </SkeletonGroup>
    );
  if (q.isError)
    return (
      <ErrorState
        title="Couldn't load autopilot settings"
        message={copyFor(q.error)}
        onRetry={() => q.refetch()}
        retrying={q.isFetching}
      />
    );
  return <Loaded data={q.data} />;
}

function Loaded({ data }: { data: Autopilot }) {
  return (
    <div className="space-y-4">
      <StatusCard data={data} />
      <RulesCard
        key={`${data.min_score}/${data.daily_apply_cap}/${data.digest_time}`}
        data={data}
      />
      <SitesCard data={data} />
    </div>
  );
}

function StatusCard({ data }: { data: Autopilot }) {
  const save = useSaveAutopilot();
  const { toast } = useToast();
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string>();

  function turnOn() {
    setError(undefined);
    save.mutate(
      { enabled: true, acknowledgement_version: data.policy_version },
      {
        onSuccess: () => {
          setAck(false);
          toast({ kind: "success", title: "Autopilot is on" });
        },
        onError: (e) => setError(copyFor(e, ERRORS)),
      },
    );
  }
  function turnOff() {
    setError(undefined);
    save.mutate(
      { enabled: false },
      {
        onSuccess: () => toast({ kind: "info", title: "Autopilot is off" }),
        onError: (e) => setError(copyFor(e, ERRORS)),
      },
    );
  }

  return (
    <Card as="section" aria-labelledby="ap-status-h" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ap-status-h" className="text-section font-semibold">
          Autopilot
        </h2>
        <StatusChip tone={data.enabled ? "ok" : "neutral"}>
          {data.enabled ? "On" : "Off"}
        </StatusChip>
      </div>
      <ul className="list-disc space-y-1 pl-5 text-muted">
        {AUTOPILOT_WHAT_IT_DOES.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
      {data.enabled ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="danger" loading={save.isPending} onClick={turnOff}>
            Turn off Autopilot
          </Button>
          {data.acknowledged_version && (
            <p className="text-hint text-subtle">
              You accepted policy version {data.acknowledged_version}.
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <Checkbox
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            label={AUTOPILOT_ACK_TEXT}
          />
          <Button
            variant="primary"
            disabled={!ack}
            loading={save.isPending}
            onClick={turnOn}
          >
            Turn on Autopilot
          </Button>
        </div>
      )}
      <p role="status" aria-live="polite" className="sr-only">
        {save.isPending ? "Saving" : save.isSuccess ? "Saved" : ""}
      </p>
      {error && (
        <p role="alert" className="text-hint font-medium text-bad">
          {error}
        </p>
      )}
      <p className="text-hint text-subtle">
        See what Autopilot did in the{" "}
        <Link
          href="/autopilot/digest"
          className="text-accent-text underline underline-offset-2"
        >
          daily digest
        </Link>
        .
      </p>
    </Card>
  );
}

function RulesCard({ data }: { data: Autopilot }) {
  const save = useSaveAutopilot();
  const { toast } = useToast();
  const [minScore, setMinScore] = useState(String(data.min_score));
  const [cap, setCap] = useState(String(data.daily_apply_cap));
  const [time, setTime] = useState(data.digest_time);
  const [error, setError] = useState<string>();
  const [touched, setTouched] = useState(false);

  const min = Number(minScore);
  const capN = Number(cap);
  const errs = {
    min:
      minScore === "" || !Number.isInteger(min) || min < 0 || min > 100
        ? "Enter a whole number from 0 to 100."
        : undefined,
    cap:
      cap === "" || !Number.isInteger(capN) || capN < 1
        ? "Enter a whole number of at least 1."
        : undefined,
    time: /^([01]\d|2[0-3]):[0-5]\d$/.test(time) ? undefined : "Pick a time.",
  };
  const invalid = Boolean(errs.min || errs.cap || errs.time);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (invalid) return;
    setError(undefined);
    save.mutate(
      { min_score: min, daily_apply_cap: capN, digest_time: time },
      {
        onSuccess: () => {
          setTouched(false);
          toast({ kind: "success", title: "Autopilot rules saved" });
        },
        onError: (er) => setError(copyFor(er, ERRORS)), // inputs stay as typed
      },
    );
  }

  return (
    <Card as="section" aria-labelledby="ap-rules-h">
      <h2 id="ap-rules-h" className="text-section font-semibold">
        Rules
      </h2>
      <form
        onSubmit={submit}
        noValidate
        className="mt-3 grid gap-4 sm:grid-cols-3"
      >
        <InputField
          label="Minimum match score"
          type="number"
          inputMode="numeric"
          min={0}
          max={100}
          value={minScore}
          onChange={(e) => (setTouched(true), setMinScore(e.target.value))}
          hint="Only jobs scoring at least this are applied to."
          error={touched ? errs.min : undefined}
        />
        <InputField
          label="Daily apply cap"
          type="number"
          inputMode="numeric"
          min={1}
          value={cap}
          onChange={(e) => (setTouched(true), setCap(e.target.value))}
          hint="Most applications per day. The server may lower very high values."
          error={touched ? errs.cap : undefined}
        />
        <InputField
          label="Digest time"
          type="time"
          value={time}
          onChange={(e) => (setTouched(true), setTime(e.target.value))}
          hint="When your daily digest is ready (India time)."
          error={touched ? errs.time : undefined}
        />
        <div className="flex flex-wrap items-center gap-3 sm:col-span-3">
          <Button type="submit" variant="primary" loading={save.isPending}>
            Save rules
          </Button>
          <p role="status" aria-live="polite" className="text-hint text-subtle">
            {save.isSuccess && !touched ? "Saved." : ""}
          </p>
        </div>
        {error && (
          <p
            role="alert"
            className="text-hint font-medium text-bad sm:col-span-3"
          >
            {error}
          </p>
        )}
      </form>
    </Card>
  );
}

function SitesCard({ data }: { data: Autopilot }) {
  return (
    <Card as="section" aria-labelledby="ap-sites-h" className="space-y-4">
      <div>
        <h2 id="ap-sites-h" className="text-section font-semibold">
          Sites that need your browser extension
        </h2>
        <p className="text-muted">
          Wellfound, Naukri and Hiring Cafe are never opened by our servers.
          They run through your own browser extension, so each one needs its own
          opt-in.{" "}
          <Link
            href="/integrations#extension"
            className="text-accent-text underline underline-offset-2"
          >
            Pair your extension
          </Link>
          .
        </p>
      </div>
      <ul className="space-y-3">
        {SITE_KEYS.map((site) => (
          <li key={site}>
            <SiteRow site={site} data={data} />
          </li>
        ))}
      </ul>
    </Card>
  );
}

function SiteRow({ site, data }: { site: SiteKey; data: Autopilot }) {
  const policy = SITE_POLICY[site];
  const opt = data.sites_opt_in[site];
  const optedIn = Boolean(opt?.acknowledged);
  const paused = Boolean(opt?.paused) || data.paused_sites.includes(site);
  const save = useSaveAutopilot();
  const { toast } = useToast();
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string>();
  const headId = `site-${site}-h`;

  function run(body: Parameters<typeof save.mutate>[0], done: string) {
    setError(undefined);
    save.mutate(body, {
      onSuccess: () => {
        setAck(false);
        toast({ kind: "success", title: done });
      },
      onError: (e) => setError(copyFor(e, ERRORS)),
    });
  }

  return (
    <section
      aria-labelledby={headId}
      className="rounded-control border border-border bg-surface-2 p-3 md:p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={headId} className="font-semibold">
          {policy.label}
        </h3>
        <div className="flex flex-wrap items-center gap-1.5">
          {optedIn && <StatusChip tone="ok">Opted in</StatusChip>}
          {paused && (
            <StatusChip tone="warn">Paused: site blocked us</StatusChip>
          )}
          {!optedIn && <StatusChip>Off</StatusChip>}
        </div>
      </div>
      <p className="mt-1 text-muted">{policy.risk}</p>
      {optedIn ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {opt?.acknowledged_at && (
            <p className="text-hint text-subtle">
              Accepted {formatDate(opt.acknowledged_at)}
              {opt.policy_version ? ` (policy ${opt.policy_version})` : ""}.
            </p>
          )}
          {paused && (
            <Button
              size="sm"
              loading={save.isPending}
              onClick={() =>
                run({ resume_sites: [site] }, `${policy.label} resumed`)
              }
            >
              Resume {policy.label}
            </Button>
          )}
          <Button
            size="sm"
            variant="danger"
            loading={save.isPending}
            onClick={() =>
              run(
                { sites: { [site]: { opt_in: false } } },
                `Opted out of ${policy.label}`,
              )
            }
          >
            Opt out of {policy.label}
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <Checkbox
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            label={policy.ack}
          />
          <Button
            size="sm"
            variant="primary"
            disabled={!ack}
            loading={save.isPending}
            onClick={() =>
              run(
                {
                  sites: {
                    [site]: {
                      opt_in: true,
                      acknowledgement_version: data.policy_version,
                    },
                  },
                },
                `Opted in to ${policy.label}`,
              )
            }
          >
            Opt in to {policy.label}
          </Button>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-hint font-medium text-bad">
          {error}
        </p>
      )}
    </section>
  );
}
