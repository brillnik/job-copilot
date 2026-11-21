"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { InputField, TextareaField } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Segmented } from "@/components/ui/segmented";
import { useToast } from "@/components/ui/toast";
import { errorMessage } from "@/lib/api/errors";
import { addJob, uploadImage } from "./api";
import { jobsKey } from "./hooks";

type Mode = "url" | "text" | "image";
const MODES = [
  { value: "url", label: "Link" },
  { value: "text", label: "Paste text" },
  { value: "image", label: "Screenshot" },
] as const;

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const IMAGE_TYPES = ["image/png", "image/jpeg"];

export function validateImage(file: File): string | null {
  if (!IMAGE_TYPES.includes(file.type))
    return "Only PNG and JPEG screenshots are supported.";
  if (file.size > MAX_IMAGE_BYTES)
    return "The screenshot must be 5 MB or smaller.";
  if (file.size === 0) return "That file is empty.";
  return null;
}

export function AddJobModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { toast } = useToast();
  const [mode, setMode] = useState<Mode>("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  // Kept after a successful upload so a retry doesn't upload twice.
  const [imageId, setImageId] = useState<string | null>(null);
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [duplicateOf, setDuplicateOf] = useState<string | null>(null);

  function reset() {
    setUrl("");
    setText("");
    setFile(null);
    setImageId(null);
    setError(undefined);
    setDuplicateOf(null);
  }
  // Closing without submitting keeps the draft; only a successful add clears it.
  function close() {
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(undefined);
    setDuplicateOf(null);
    if (mode === "url" && !url.trim()) return setError("Enter the job link.");
    if (mode === "text" && !text.trim())
      return setError("Paste the job description.");
    if (mode === "image") {
      if (!file) return setError("Choose a screenshot to upload.");
      const problem = validateImage(file);
      if (problem) return setError(problem);
    }
    setBusy(true);
    try {
      let result;
      if (mode === "url")
        result = await addJob({ source: "url", url: url.trim() });
      else if (mode === "text") result = await addJob({ source: "text", text });
      else {
        const id = imageId ?? (await uploadImage(file as File));
        setImageId(id);
        result = await addJob({ source: "image", image_id: id });
      }
      void qc.invalidateQueries({ queryKey: jobsKey });
      if (result.duplicate) {
        setDuplicateOf(result.job_id);
        return;
      }
      toast({
        kind: "success",
        title: "Job added",
        description: "We're reading the posting. It will appear in your inbox.",
      });
      reset();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={close}
      title="Add a job"
      description="Add a posting by link, pasted text or a screenshot."
      footer={
        <>
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="add-job-form"
            variant="primary"
            loading={busy}
          >
            Add job
          </Button>
        </>
      }
    >
      <form
        id="add-job-form"
        onSubmit={submit}
        noValidate
        className="flex flex-col gap-4"
      >
        <Segmented<Mode>
          label="Add job from"
          options={MODES}
          value={mode}
          onChange={(m) => {
            setMode(m);
            setError(undefined);
            setDuplicateOf(null);
          }}
          className="self-start"
        />
        {mode === "url" && (
          <InputField
            label="Job link"
            inputMode="url"
            autoComplete="off"
            placeholder="https://company.com/careers/role"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            error={error}
          />
        )}
        {mode === "text" && (
          <TextareaField
            label="Job description"
            rows={8}
            maxLength={100000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            error={error}
          />
        )}
        {mode === "image" && (
          <div>
            <label
              htmlFor="add-job-image"
              className="mb-1.5 block text-[13px] font-medium"
            >
              Screenshot file
            </label>
            <input
              id="add-job-image"
              type="file"
              accept="image/png,image/jpeg"
              aria-describedby="add-job-image-hint"
              aria-invalid={error ? true : undefined}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setImageId(null);
                setError(undefined);
              }}
              className="block w-full rounded-control border border-border-strong bg-surface p-2 text-body file:mr-3 file:rounded-control file:border-0 file:bg-surface-2 file:px-3 file:py-2 file:font-medium file:text-text"
            />
            <p id="add-job-image-hint" className="mt-1.5 text-hint text-subtle">
              PNG or JPEG, up to 5 MB.
            </p>
            {error && (
              <p role="alert" className="mt-1.5 text-hint font-medium text-bad">
                {error}
              </p>
            )}
          </div>
        )}
        <div aria-live="polite">
          {duplicateOf && (
            <p className="rounded-control bg-accent-soft p-3 text-accent-text">
              You&apos;ve already added this job.{" "}
              <Link
                href={`/jobs/${duplicateOf}`}
                className="font-semibold underline"
              >
                Open the existing job
              </Link>
            </p>
          )}
        </div>
      </form>
    </Modal>
  );
}
