"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CheckboxGroup } from "@/components/ui/checkbox-group";
import { InputField } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { TagInput } from "@/components/ui/tag-input";
import { useToast } from "@/components/ui/toast";
import { ApiError } from "@/lib/api/errors";
import { type SettingsOut, settingsKey } from "@/hooks/use-settings";
import { useQueryClient } from "@tanstack/react-query";
import { useSavePreferences } from "./api";
import {
  CITIES,
  COVERAGE_TARGETS,
  DAILY_CAP_MAX,
  type FormValues,
  preferencesSchema,
  toFormValues,
  toPreferences,
} from "./schema";

const LENGTH_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "1", label: "1 page" },
  { value: "2", label: "2 pages" },
  { value: "3", label: "3 pages" },
] as const;
const TEMPLATE_OPTIONS = [
  { value: "classic", label: "Classic" },
  { value: "compact", label: "Compact" },
] as const;
const COVERAGE_OPTIONS = COVERAGE_TARGETS.map((v) => ({
  value: v,
  label: `${Math.round(Number(v) * 100)}%`,
}));

function resetsAt(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "tomorrow"
    : d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Mirrors the server's bounds (see schema.ts). User input is never discarded on failure. */
export function PreferencesForm({ settings }: { settings: SettingsOut }) {
  const { toast } = useToast();
  const qc = useQueryClient();
  const save = useSavePreferences();
  const form = useForm<FormValues>({
    resolver: zodResolver(preferencesSchema),
    defaultValues: toFormValues(settings.preferences as never),
    mode: "onTouched",
  });
  const { control, register, formState } = form;
  const [stale, setStale] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [status, setStatus] = useState("");

  // Theme is owned by the Appearance card; always send the freshest account value.
  function latest(): SettingsOut {
    return qc.getQueryData<SettingsOut>(settingsKey) ?? settings;
  }

  async function submit(values: FormValues, overwrite = false) {
    setServerError(null);
    setStale(false);
    const cur = overwrite ? await refetchLatest() : latest();
    try {
      const out = await save.mutateAsync({
        body: toPreferences(values, cur.preferences.theme),
        rev: cur.rev,
      });
      form.reset(toFormValues(out.preferences as never));
      setStatus("Preferences saved.");
      toast({ kind: "success", title: "Preferences saved" });
    } catch (e) {
      setStatus("");
      if (e instanceof ApiError && e.code === "stale_write") setStale(true);
      else
        setServerError(
          e instanceof ApiError
            ? e.message
            : "Couldn't save. Check your connection and try again.",
        );
    }
  }

  async function refetchLatest(): Promise<SettingsOut> {
    await qc.invalidateQueries({ queryKey: settingsKey });
    return latest();
  }

  const used = settings.runs_used_today;
  const cap = settings.daily_cap;

  return (
    <form
      noValidate
      aria-labelledby="prefs-h"
      onSubmit={form.handleSubmit((v) => submit(v))}
      className="flex flex-col gap-4"
    >
      <Card className="flex flex-col gap-5">
        <div>
          <h2 id="prefs-h" className="text-section font-semibold">
            Job preferences
          </h2>
          <p className="text-muted">
            Used to find and score jobs for you. Changes re-score open jobs.
          </p>
        </div>

        <Controller
          control={control}
          name="target_roles"
          render={({ field, fieldState }) => (
            <TagInput
              label="Target roles"
              values={field.value}
              onChange={field.onChange}
              max={10}
              placeholder="e.g. Frontend Engineer"
              addLabel="Add role"
              error={
                fieldState.error?.message ??
                (Array.isArray(formState.errors.target_roles)
                  ? "Each role must be 1 to 80 characters"
                  : undefined)
              }
            />
          )}
        />
        <Controller
          control={control}
          name="cities"
          render={({ field, fieldState }) => (
            <CheckboxGroup
              legend="Cities"
              options={CITIES}
              values={field.value}
              onChange={field.onChange}
              hint="Pick every city you'd work in. “Remote” counts as a city."
              error={fieldState.error?.message}
            />
          )}
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <InputField
            label="Current CTC (LPA)"
            type="number"
            inputMode="decimal"
            step="any"
            min={0}
            max={500}
            error={formState.errors.current_ctc_lpa?.message}
            {...register("current_ctc_lpa", { valueAsNumber: true })}
          />
          <InputField
            label="Expected CTC (LPA)"
            type="number"
            inputMode="decimal"
            step="any"
            min={0}
            max={500}
            error={formState.errors.expected_ctc_lpa?.message}
            {...register("expected_ctc_lpa", { valueAsNumber: true })}
          />
          <InputField
            label="Notice period (days)"
            type="number"
            inputMode="numeric"
            min={0}
            max={180}
            error={formState.errors.notice_days?.message}
            {...register("notice_days", { valueAsNumber: true })}
          />
        </div>
      </Card>

      <Card className="flex flex-col gap-5">
        <div>
          <h2 className="text-section font-semibold">Resume defaults</h2>
          <p className="text-muted">
            Applied to new tailored resumes. You can change length per job.
          </p>
        </div>
        <Controller
          control={control}
          name="default_length"
          render={({ field }) => (
            <Segmented
              label="Default length"
              options={LENGTH_OPTIONS}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
        <Controller
          control={control}
          name="template"
          render={({ field }) => (
            <Segmented
              label="Template"
              options={TEMPLATE_OPTIONS}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
        <div>
          <Controller
            control={control}
            name="coverage_target"
            render={({ field }) => (
              <Segmented
                label="Coverage target"
                options={COVERAGE_OPTIONS}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <p className="mt-1.5 text-hint text-subtle">
            Drafts that cover less than this share of the job&apos;s must-haves
            are flagged for review.
          </p>
        </div>
      </Card>

      <Card className="flex flex-col gap-3">
        <div>
          <h2 className="text-section font-semibold">Daily limit</h2>
          <p role="status" className="text-muted">
            Used today:{" "}
            <span className="font-mono font-semibold text-text tabular-nums">
              {used} of {cap}
            </span>{" "}
            resumes. Resets at {resetsAt(settings.cap_resets_at)}.
          </p>
        </div>
        <InputField
          className="max-w-48"
          label="Resumes per day"
          type="number"
          inputMode="numeric"
          min={1}
          max={DAILY_CAP_MAX}
          hint={`1 to ${DAILY_CAP_MAX}. Applies from the next run.`}
          error={formState.errors.daily_cap?.message}
          {...register("daily_cap", { valueAsNumber: true })}
        />
      </Card>

      {stale && (
        <Card
          role="alert"
          className="flex flex-col items-start gap-2 border-warn"
        >
          <p className="font-semibold">Your settings changed somewhere else.</p>
          <p className="text-muted">
            Your edits are still in the form. Choose what to do:
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              onClick={() => void form.handleSubmit((v) => submit(v, true))()}
            >
              Save my changes anyway
            </Button>
            <Button
              onClick={async () => {
                const fresh = await refetchLatest();
                form.reset(toFormValues(fresh.preferences as never));
                setStale(false);
              }}
            >
              Discard mine and load latest
            </Button>
          </div>
        </Card>
      )}
      <div role="alert">
        {serverError && <p className="font-medium text-bad">{serverError}</p>}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" loading={save.isPending}>
          Save preferences
        </Button>
        <p role="status" aria-live="polite" className="text-hint text-muted">
          {status || (formState.isDirty ? "You have unsaved changes." : "")}
        </p>
      </div>
    </form>
  );
}
