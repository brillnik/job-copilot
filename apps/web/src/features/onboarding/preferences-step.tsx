"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ErrorState } from "@/components/ui/error-state";
import { InputField } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import {
  settingsKey,
  updatePreferences,
  useSettings,
  type SettingsOut,
} from "@/hooks/use-settings";
import { errorMessage } from "@/lib/api/errors";
import { fieldErrors } from "@/lib/api/field-errors";
import { useTheme } from "@/providers/theme-provider";
import {
  cityOptions,
  PREF_FIELD,
  toPrefValues,
  toPreferences,
  validatePrefs,
  type PrefErrors,
  type PrefValues,
} from "./preferences-model";
import { RoleInput } from "./role-input";

function PrefsForm({ settings }: { settings: SettingsOut }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { theme } = useTheme();
  const [v, setV] = useState<PrefValues>(() => toPrefValues(settings.preferences));
  const [errors, setErrors] = useState<PrefErrors>({});
  const [formError, setFormError] = useState<string>();
  const set = <K extends keyof PrefValues>(k: K, val: PrefValues[K]) =>
    setV((p) => ({ ...p, [k]: val }));

  const save = useMutation({
    // Unconfigured users only have server defaults, so keep the theme they picked locally.
    mutationFn: () =>
      updatePreferences({
        ...toPreferences(v),
        ...(settings.configured ? {} : { theme }),
      }),
    onSuccess: (data) => {
      qc.setQueryData(settingsKey, data);
      router.push("/");
    },
    onError: (e) => {
      const fe = fieldErrors(e);
      const mapped: PrefErrors = {};
      for (const [path, msg] of Object.entries(fe)) {
        const key = PREF_FIELD[path.split(".")[0]];
        if (key) mapped[key] ??= msg;
      }
      setErrors(mapped);
      setFormError(Object.keys(mapped).length ? undefined : errorMessage(e));
    },
  });

  const options = cityOptions(settings.preferences.cities);

  return (
    <form
      noValidate
      className="flex flex-col gap-6"
      onSubmit={(e) => {
        e.preventDefault();
        const found = validatePrefs(v);
        setErrors(found);
        setFormError(undefined);
        if (Object.keys(found).length === 0) save.mutate();
      }}
    >
      <section className="flex flex-col gap-5 rounded-card border border-border bg-surface p-5">
        <RoleInput
          roles={v.roles}
          onChange={(r) => set("roles", r)}
          error={errors.roles}
        />

        <fieldset aria-describedby={errors.cities ? "cities-err" : undefined}>
          <legend className="mb-1.5 text-[13px] font-medium">
            Cities you&apos;d work from
          </legend>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            {options.map((c) => (
              <Checkbox
                key={c}
                label={c}
                checked={v.cities.includes(c)}
                onChange={(e) =>
                  set(
                    "cities",
                    e.target.checked
                      ? [...v.cities, c]
                      : v.cities.filter((x) => x !== c),
                  )
                }
              />
            ))}
          </div>
          {errors.cities && (
            <p id="cities-err" role="alert" className="mt-1.5 text-hint font-medium text-bad">
              {errors.cities}
            </p>
          )}
        </fieldset>
      </section>

      <section className="grid gap-5 rounded-card border border-border bg-surface p-5 sm:grid-cols-3">
        <InputField
          label="Current CTC (LPA)"
          hint="Lakhs per year. Only you see this."
          inputMode="decimal"
          className="[&_input]:font-mono"
          value={v.currentCtc}
          error={errors.currentCtc}
          onChange={(e) => set("currentCtc", e.target.value)}
        />
        <InputField
          label="Expected CTC (LPA)"
          inputMode="decimal"
          className="[&_input]:font-mono"
          value={v.expectedCtc}
          error={errors.expectedCtc}
          onChange={(e) => set("expectedCtc", e.target.value)}
        />
        <InputField
          label="Notice period (days)"
          inputMode="numeric"
          className="[&_input]:font-mono"
          value={v.noticeDays}
          error={errors.noticeDays}
          onChange={(e) => set("noticeDays", e.target.value)}
        />
      </section>

      <section className="flex flex-col gap-5 rounded-card border border-border bg-surface p-5">
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium" aria-hidden="true">
            Default resume length
          </span>
          <Segmented
            label="Default resume length"
            value={v.defaultLength}
            onChange={(x) => set("defaultLength", x)}
            options={[
              { value: "auto", label: "Auto" },
              { value: "1", label: "1 page" },
              { value: "2", label: "2 pages" },
              { value: "3", label: "3 pages" },
            ]}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium" aria-hidden="true">
            Template
          </span>
          <Segmented
            label="Template"
            value={v.template}
            onChange={(x) => set("template", x)}
            options={[
              { value: "classic", label: "Classic" },
              { value: "compact", label: "Compact" },
            ]}
          />
        </div>
      </section>

      {(formError || (save.isError && Object.keys(errors).length === 0)) && (
        <ErrorState
          title="Couldn't save your preferences"
          message={`${formError ?? errorMessage(save.error)} Your answers are still here.`}
          onRetry={() => save.mutate()}
          retrying={save.isPending}
        />
      )}

      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" loading={save.isPending}>
          Save and go to inbox
        </Button>
      </div>
    </form>
  );
}

export function PreferencesStep() {
  const settings = useSettings();
  return (
    <>
      <PageHeader
        level="screen"
        eyebrow="Step 3 of 3"
        title="Your preferences"
        description="These decide which jobs we surface and how your resumes are laid out. You can change them any time in Settings."
      />
      {settings.isPending ? (
        <SkeletonGroup label="Loading your preferences" className="flex flex-col gap-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-28 w-full" />
        </SkeletonGroup>
      ) : settings.isError ? (
        <ErrorState
          title="Couldn't load your preferences"
          message={errorMessage(settings.error)}
          onRetry={() => void settings.refetch()}
          retrying={settings.isFetching}
        />
      ) : (
        <PrefsForm settings={settings.data} />
      )}
    </>
  );
}
