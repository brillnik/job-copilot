"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createContext, useContext, useState } from "react";
import {
  FormProvider,
  get,
  useFieldArray,
  useForm,
  useFormContext,
  useWatch,
} from "react-hook-form";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { InputField, TextareaField } from "@/components/ui/field";
import { AlertIcon } from "@/components/ui/icons";
import {
  approveDraft,
  approvedKey,
  draftKey,
  fetchDraft,
  putDraft,
  useDraftProfile,
  type ProfileOut,
} from "@/hooks/use-profile";
import { errorMessage, isApiError } from "@/lib/api/errors";
import { fieldErrors } from "@/lib/api/field-errors";
import {
  findFlags,
  toFormPath,
  toFormValues,
  toProfileData,
  unresolvedFlags,
  type FormValues,
  type ReviewFlag,
} from "@/features/profile/profile-model";
import { ONBOARDING_PATHS } from "./constants";
import { PageLoading } from "./setup-gate";

type Confirmations = {
  flags: Map<string, ReviewFlag>;
  confirmed: Set<string>;
  toggle: (path: string) => void;
};
const ConfirmCtx = createContext<Confirmations | null>(null);
const errorAt = (errors: object, path: string) =>
  (get(errors, path) as { message?: string } | undefined)?.message;
const useConfirm = () => useContext(ConfirmCtx)!;

/** The "this is fine as it is" checkbox for a flagged value. */
function FlagConfirm({ path, showReason }: { path: string; showReason?: boolean }) {
  const { flags, confirmed, toggle } = useConfirm();
  const flag = flags.get(path);
  if (!flag) return null;
  const ok = confirmed.has(path);
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {showReason && !ok && (
        <p className="flex items-center gap-1.5 text-hint font-medium text-warn">
          <AlertIcon className="size-3.5" />
          {flag.reason}
        </p>
      )}
      <Checkbox
        label={flag.confirmLabel}
        checked={ok}
        onChange={() => toggle(path)}
      />
    </div>
  );
}

function RField({
  path,
  label,
  textarea,
  required,
  hint,
  type,
}: {
  path: string;
  label: string;
  textarea?: boolean;
  required?: string;
  hint?: string;
  type?: string;
}) {
  const { register, formState } = useFormContext<FormValues>();
  const { flags, confirmed } = useConfirm();
  const flag = flags.get(path);
  const error = errorAt(formState.errors, path);
  const common = {
    label,
    hint,
    error,
    lowConfidence: !!flag && !confirmed.has(path),
    flagText: flag?.reason,
    ...register(path as never, required ? { required } : undefined),
  };
  return (
    <div id={`field-${path}`} className="min-w-0">
      {textarea ? <TextareaField {...common} /> : <InputField type={type} {...common} />}
      <FlagConfirm path={path} />
    </div>
  );
}

function BulletsEditor({ name, noun }: { name: string; noun: string }) {
  const { control, register, formState } = useFormContext<FormValues>();
  const { fields, append, remove } = useFieldArray({
    control,
    name: name as "experience.0.bullets",
    keyName: "_key",
  });
  return (
    <div className="flex flex-col gap-3">
      <h4 className="text-[13px] font-medium">Achievements</h4>
      {fields.map((f, i) => {
        const p = `${name}.${i}.text`;
        return (
          <div key={f._key} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-2">
            <TextareaField
              className="min-w-0 flex-1"
              label={`${noun} achievement ${i + 1}`}
              error={errorAt(formState.errors, p)}
              {...register(p as never, {
                required: "Write the achievement or remove it",
                maxLength: { value: 1000, message: "Keep it under 1000 characters" },
              })}
            />
            <Button
              variant="ghost"
              size="sm"
              className="sm:mt-6"
              onClick={() => remove(i)}
              aria-label={`Remove ${noun} achievement ${i + 1}`}
            >
              Remove
            </Button>
          </div>
        );
      })}
      <FlagConfirm path={name} showReason />
      <div>
        <Button size="sm" onClick={() => append({ text: "" } as never)}>
          Add achievement
        </Button>
      </div>
    </div>
  );
}

function Section({ title, children, action }: { title: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <Card as="section" className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-section font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </Card>
  );
}

const grid = "grid gap-4 sm:grid-cols-2";

function ReviewForm({ draft }: { draft: ProfileOut }) {
  const router = useRouter();
  const qc = useQueryClient();
  const form = useForm<FormValues>({ defaultValues: toFormValues(draft.data) });
  const { control, handleSubmit, setError, reset } = form;
  const values = useWatch({ control }) as FormValues;
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});

  const exp = useFieldArray({ control, name: "experience", keyName: "_key" });
  const proj = useFieldArray({ control, name: "projects", keyName: "_key" });
  const edu = useFieldArray({ control, name: "education", keyName: "_key" });

  const flagList = findFlags(values);
  const flags = new Map(flagList.map((f) => [f.path, f]));
  const open = unresolvedFlags(flagList, confirmed);
  const toggle = (path: string) =>
    setConfirmed((s) => {
      const n = new Set(s);
      if (!n.delete(path)) n.add(path);
      return n;
    });
  // Index-based paths shift when an entry is removed, so start over then.
  const removeEntry = (fn: () => void) => {
    setConfirmed(new Set());
    fn();
  };

  const save = useMutation({
    mutationFn: async (v: FormValues) => {
      await putDraft(toProfileData(v));
      return approveDraft();
    },
    onSuccess: (approved) => {
      qc.setQueryData(approvedKey, approved);
      qc.setQueryData(draftKey, null);
      router.push(ONBOARDING_PATHS.preferences);
    },
    onError: (e) => {
      const errs = fieldErrors(e);
      setServerErrors(errs);
      for (const [p, message] of Object.entries(errs))
        if (p) setError(toFormPath(p) as never, { type: "server", message });
    },
  });
  const submit = handleSubmit((v) => {
    setServerErrors({});
    save.mutate(v);
  });

  const reload = useMutation({
    mutationFn: async () => {
      const fresh = await qc.fetchQuery({
        queryKey: draftKey,
        queryFn: fetchDraft,
        staleTime: 0,
      });
      if (fresh) reset(toFormValues(fresh.data));
      setConfirmed(new Set());
      save.reset();
    },
  });

  const err = save.error;
  const stale = isApiError(err) && err.isStaleWrite;
  const hasFieldErrors = Object.keys(serverErrors).length > 0;

  return (
    <ConfirmCtx.Provider value={{ flags, confirmed, toggle }}>
      <FormProvider {...form}>
        <PageHeader
          level="screen"
          eyebrow="Step 2 of 3"
          title="Check your profile"
          description="This is what we read from your resume. Fix anything wrong. Every tailored resume is built only from what you approve here."
        />
        <form noValidate onSubmit={submit} className="flex flex-col gap-5">
          <div role="status" aria-live="polite" className="rounded-card border border-border bg-surface p-4">
            {open.length === 0 ? (
              <p className="font-medium text-ok">All items checked. You can continue.</p>
            ) : (
              <>
                <p className="font-medium">
                  {open.length} {open.length === 1 ? "item needs" : "items need"} your confirmation
                </p>
                <ul className="mt-2 list-disc pl-5 text-muted">
                  {open.map((f) => (
                    <li key={f.path}>
                      <a className="text-accent-text underline" href={`#field-${f.path}`}>
                        {f.label}
                      </a>
                      : {f.reason}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          <Section title="Contact">
            <div className={grid}>
              <RField path="contact.name" label="Full name" />
              <RField path="contact.email" label="Email" type="email" />
              <RField path="contact.phone" label="Phone" type="tel" />
              <RField path="contact.location" label="Location" />
            </div>
            <RField
              path="contact.linksText"
              label="Links"
              textarea
              hint="One per line: LinkedIn, GitHub, portfolio."
            />
          </Section>

          <Section title="Summary">
            <RField path="summary" label="Professional summary" textarea />
          </Section>

          <Section
            title="Experience"
            action={
              <Button
                size="sm"
                onClick={() =>
                  exp.append({ company: "", title: "", location: "", start: "", end: "", bullets: [] } as never)
                }
              >
                Add role
              </Button>
            }
          >
            {exp.fields.length === 0 && (
              <>
                <p className="text-muted">No work experience was found.</p>
                <FlagConfirm path="experience" />
              </>
            )}
            {exp.fields.map((f, i) => (
              <div key={f._key} className="flex flex-col gap-4 rounded-control border border-border p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">Role {i + 1}</h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove role ${i + 1}`}
                    onClick={() => removeEntry(() => exp.remove(i))}
                  >
                    Remove role
                  </Button>
                </div>
                <div className={grid}>
                  <RField path={`experience.${i}.company`} label="Company" required="Company is required" />
                  <RField path={`experience.${i}.title`} label="Job title" />
                  <RField path={`experience.${i}.location`} label="Location" />
                  <div className={grid}>
                    <RField path={`experience.${i}.start`} label="Start" hint="e.g. Jun 2021" />
                    <RField path={`experience.${i}.end`} label="End" hint="or Present" />
                  </div>
                </div>
                <BulletsEditor name={`experience.${i}.bullets`} noun={`Role ${i + 1}`} />
              </div>
            ))}
          </Section>

          <Section
            title="Projects"
            action={
              <Button
                size="sm"
                onClick={() => proj.append({ name: "", description: "", bullets: [] } as never)}
              >
                Add project
              </Button>
            }
          >
            {proj.fields.length === 0 && <p className="text-muted">No projects.</p>}
            {proj.fields.map((f, i) => (
              <div key={f._key} className="flex flex-col gap-4 rounded-control border border-border p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">Project {i + 1}</h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove project ${i + 1}`}
                    onClick={() => removeEntry(() => proj.remove(i))}
                  >
                    Remove project
                  </Button>
                </div>
                <RField path={`projects.${i}.name`} label="Project name" required="Project name is required" />
                <RField path={`projects.${i}.description`} label="Description" textarea />
                <BulletsEditor name={`projects.${i}.bullets`} noun={`Project ${i + 1}`} />
              </div>
            ))}
          </Section>

          <Section
            title="Education"
            action={
              <Button
                size="sm"
                onClick={() => edu.append({ institution: "", degree: "", start: "", end: "" } as never)}
              >
                Add education
              </Button>
            }
          >
            {edu.fields.length === 0 && <p className="text-muted">No education.</p>}
            {edu.fields.map((f, i) => (
              <div key={f._key} className="flex flex-col gap-4 rounded-control border border-border p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">Education {i + 1}</h3>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label={`Remove education ${i + 1}`}
                    onClick={() => removeEntry(() => edu.remove(i))}
                  >
                    Remove education
                  </Button>
                </div>
                <div className={grid}>
                  <RField path={`education.${i}.institution`} label="Institution" required="Institution is required" />
                  <RField path={`education.${i}.degree`} label="Degree" />
                  <RField path={`education.${i}.start`} label="Start" />
                  <RField path={`education.${i}.end`} label="End" />
                </div>
              </div>
            ))}
          </Section>

          <Section title="Skills">
            <RField
              path="skillsText"
              label="Skills"
              textarea
              hint="Separate with commas. Only skills listed here can appear on a tailored resume."
            />
          </Section>

          {hasFieldErrors && (
            <div role="alert" className="rounded-card border border-bad bg-bad-soft p-4 text-bad">
              <p className="font-semibold">The server rejected some values. Fix them and try again.</p>
              <ul className="mt-1 list-disc pl-5">
                {Object.entries(serverErrors).map(([p, m]) => (
                  <li key={p}>
                    {p ? `${p.replace(/\./g, " ")}: ` : ""}
                    {m}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {err && !hasFieldErrors && stale && (
            <ErrorState
              title="This profile changed somewhere else"
              message="Another tab or device updated your draft. Load the latest version to continue, or keep your edits here and save again."
              onRetry={() => reload.mutate()}
              retrying={reload.isPending}
            />
          )}
          {err && !hasFieldErrors && !stale && (
            <ErrorState
              title="Couldn't save your profile"
              message={`${errorMessage(err)} Your edits are still here.`}
              onRetry={() => void submit()}
              retrying={save.isPending}
            />
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="submit"
              variant="primary"
              disabled={open.length > 0}
              loading={save.isPending}
              aria-describedby="continue-note"
            >
              Approve and continue
            </Button>
            <Link
              href={ONBOARDING_PATHS.upload}
              className="inline-flex min-h-11 items-center text-accent-text underline"
            >
              Upload a different resume
            </Link>
            <p id="continue-note" className="text-hint text-subtle">
              {open.length > 0
                ? "Confirm or fix the items above to continue."
                : "Approving saves this as your profile."}
            </p>
          </div>
        </form>
      </FormProvider>
    </ConfirmCtx.Provider>
  );
}

export function ReviewStep() {
  const draft = useDraftProfile();
  if (draft.isPending) return <PageLoading label="Loading your draft profile" />;
  if (draft.isError)
    return (
      <ErrorState
        title="Couldn't load your draft"
        message={errorMessage(draft.error)}
        onRetry={() => void draft.refetch()}
        retrying={draft.isFetching}
      />
    );
  if (draft.data === null)
    return (
      <EmptyState
        title="No draft to review"
        description="Upload a resume and we'll build a draft profile for you to check."
        action={
          <Link
            href={ONBOARDING_PATHS.upload}
            className="inline-flex min-h-11 items-center rounded-control border border-accent bg-accent px-4 font-medium text-on-accent"
          >
            Upload a resume
          </Link>
        }
      />
    );
  return <ReviewForm draft={draft.data} />;
}
