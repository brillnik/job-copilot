"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Dropzone } from "@/components/ui/dropzone";
import { ErrorState } from "@/components/ui/error-state";
import { LongTaskStatus } from "@/components/ui/long-task-status";
import { draftKey, putDraft, uploadResume } from "@/hooks/use-profile";
import { errorMessage, isApiError } from "@/lib/api/errors";
import { EMPTY_PROFILE } from "@/features/profile/profile-model";
import { ONBOARDING_PATHS } from "./constants";
import { formatBytes, RESUME_ACCEPT, validateResumeFile } from "./resume-file";

const isAbort = (e: unknown) =>
  (e instanceof DOMException && e.name === "AbortError") ||
  (e instanceof Error && e.name === "AbortError");

function failureTitle(e: unknown) {
  if (!isApiError(e)) return "Couldn't upload your resume";
  switch (e.code) {
    case "unsupported_file_type":
      return "That file type isn't supported";
    case "file_too_large":
      return "That file is too large";
    case "empty_file":
      return "That file is empty";
    case "extraction_failed":
      return "We couldn't read this resume";
    case "extraction_unavailable":
      return "Resume reading isn't available right now";
    default:
      return "Couldn't upload your resume";
  }
}

export function UploadStep() {
  const router = useRouter();
  const qc = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string>();
  const abort = useRef<AbortController | null>(null);
  const [stopped, setStopped] = useState(false);

  const done = () => router.push(ONBOARDING_PATHS.review);

  const upload = useMutation({
    mutationFn: (f: File) => {
      abort.current = new AbortController();
      return uploadResume(f, abort.current.signal);
    },
    onSuccess: (draft) => {
      qc.setQueryData(draftKey, draft);
      done();
    },
  });
  // "Start without a resume": an empty draft created through PUT /profile/draft.
  const blank = useMutation({
    mutationFn: () => putDraft(EMPTY_PROFILE),
    onSuccess: (draft) => {
      qc.setQueryData(draftKey, draft);
      done();
    },
  });

  function choose(f: File) {
    setStopped(false);
    upload.reset();
    const problem = validateResumeFile(f);
    setFileError(problem ?? undefined);
    setFile(problem ? null : f);
  }

  const reading = upload.isPending;
  const failure = upload.isError && !isAbort(upload.error) ? upload.error : null;

  return (
    <>
      <PageHeader
        level="screen"
        eyebrow="Step 1 of 3"
        title="Upload your resume"
        description="We read it once to build your profile. You review and correct everything before it is used."
      />

      {reading ? (
        <LongTaskStatus
          label="Reading your resume…"
          slowMessage="Still working. Reading a resume can take a few minutes on some setups. You can keep this tab open."
          action={
            <Button
              variant="ghost"
              onClick={() => {
                abort.current?.abort();
                setStopped(true);
              }}
            >
              Stop waiting
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-4">
          <Dropzone
            label="Drop your resume here"
            hint="PDF or DOCX, up to 5 MB. Images and scans are not supported yet."
            accept={RESUME_ACCEPT}
            onFile={choose}
            error={fileError}
            selected={
              file ? { name: file.name, detail: formatBytes(file.size) } : null
            }
          />

          {stopped && (
            <p role="status" className="text-muted">
              Stopped waiting. The server may still finish reading it in the
              background; you can try again.
            </p>
          )}

          {failure && (
            <ErrorState
              title={failureTitle(failure)}
              message={errorMessage(failure)}
              onRetry={file ? () => upload.mutate(file) : undefined}
            />
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button
              variant="primary"
              disabled={!file}
              onClick={() => file && upload.mutate(file)}
            >
              Read my resume
            </Button>
            <Button
              variant="ghost"
              loading={blank.isPending}
              onClick={() => blank.mutate()}
            >
              Start without a resume
            </Button>
          </div>
          {blank.isError && (
            <p role="alert" className="text-hint font-medium text-bad">
              {errorMessage(blank.error)}
            </p>
          )}
        </div>
      )}
    </>
  );
}
