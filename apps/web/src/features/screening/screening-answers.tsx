"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { InputField, TextareaField } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { copyFor } from "@/features/common/error-copy";
import { formatDate, humanize } from "@/features/common/format";
import {
  type ScreeningAnswer,
  useDeleteScreeningAnswer,
  useSaveScreeningAnswer,
  useScreeningAnswers,
} from "./hooks";

const ERRORS = {
  not_found: "That answer no longer exists. Reload the list.",
  validation_error:
    "The answer must be 1 to 4000 characters and the question up to 1000.",
};

export function ScreeningAnswers() {
  const q = useScreeningAnswers();
  const [editing, setEditing] = useState<ScreeningAnswer | null>(null);
  const [deleting, setDeleting] = useState<ScreeningAnswer | null>(null);

  return (
    <section aria-labelledby="screening-h" className="space-y-3">
      <div>
        <h2 id="screening-h" className="text-section font-semibold">
          Screening answers
        </h2>
        <p className="text-muted">
          Answers we reuse when an application form asks the same question. Edit
          or delete them any time; answers you edit count as your own.
        </p>
      </div>
      {q.isPending ? (
        <SkeletonGroup label="Loading screening answers" className="space-y-2">
          <Skeleton className="h-20 rounded-card" />
          <Skeleton className="h-20 rounded-card" />
        </SkeletonGroup>
      ) : q.isError ? (
        <ErrorState
          title="Couldn't load screening answers"
          message={copyFor(q.error)}
          onRetry={() => q.refetch()}
          retrying={q.isFetching}
        />
      ) : q.data.length === 0 ? (
        <EmptyState
          title="No saved answers yet"
          description="When an application asks a question we can't answer, your reply is saved here for next time."
        />
      ) : (
        <ul className="space-y-2" aria-label="Saved screening answers">
          {q.data.map((a) => (
            <li key={a.id}>
              <AnswerRow
                answer={a}
                onEdit={setEditing}
                onDelete={setDeleting}
              />
            </li>
          ))}
        </ul>
      )}
      <EditDialog answer={editing} onClose={() => setEditing(null)} />
      <DeleteDialog answer={deleting} onClose={() => setDeleting(null)} />
    </section>
  );
}

export function AnswerRow({
  answer,
  onEdit,
  onDelete,
}: {
  answer: ScreeningAnswer;
  onEdit: (a: ScreeningAnswer) => void;
  onDelete: (a: ScreeningAnswer) => void;
}) {
  return (
    <Card className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div className="min-w-0 flex-1">
        <p className="font-medium">{answer.question}</p>
        <p className="mt-1 break-words text-muted">{answer.answer}</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <Chip>{humanize(answer.source)}</Chip>
          <Chip>{humanize(answer.field_type)}</Chip>
          <span className="text-hint text-subtle">
            Updated {formatDate(answer.updated_at)}
          </span>
        </div>
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onEdit(answer)}>
          Edit<span className="sr-only"> answer: {answer.question}</span>
        </Button>
        <Button size="sm" variant="danger" onClick={() => onDelete(answer)}>
          Delete<span className="sr-only"> answer: {answer.question}</span>
        </Button>
      </div>
    </Card>
  );
}

function EditDialog({
  answer,
  onClose,
}: {
  answer: ScreeningAnswer | null;
  onClose: () => void;
}) {
  // Re-mount the form per answer so its fields start from that answer.
  return (
    <Modal
      open={answer !== null}
      onClose={onClose}
      title="Edit answer"
      variant="sheet"
    >
      {answer && <EditForm key={answer.id} answer={answer} onClose={onClose} />}
    </Modal>
  );
}

function EditForm({
  answer,
  onClose,
}: {
  answer: ScreeningAnswer;
  onClose: () => void;
}) {
  const save = useSaveScreeningAnswer();
  const { toast } = useToast();
  const [question, setQuestion] = useState(answer.question);
  const [text, setText] = useState(answer.answer);
  const [error, setError] = useState<string>();
  const [fieldError, setFieldError] = useState<string>();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return setFieldError("Enter an answer.");
    if (!question.trim()) return setFieldError("Enter the question.");
    setFieldError(undefined);
    setError(undefined);
    save.mutate(
      {
        id: answer.id,
        answer: text.trim(),
        question:
          question.trim() !== answer.question ? question.trim() : undefined,
      },
      {
        onSuccess: () => {
          toast({ kind: "success", title: "Answer saved" });
          onClose();
        },
        onError: (er) => setError(copyFor(er, ERRORS)), // the form keeps what was typed
      },
    );
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <InputField
        label="Question"
        value={question}
        maxLength={1000}
        onChange={(e) => setQuestion(e.target.value)}
      />
      <TextareaField
        label="Answer"
        value={text}
        maxLength={4000}
        onChange={(e) => setText(e.target.value)}
        error={fieldError}
      />
      {error && (
        <p role="alert" className="text-hint font-medium text-bad">
          {error}
        </p>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={save.isPending}>
          Save answer
        </Button>
      </div>
    </form>
  );
}

function DeleteDialog({
  answer,
  onClose,
}: {
  answer: ScreeningAnswer | null;
  onClose: () => void;
}) {
  const del = useDeleteScreeningAnswer();
  const { toast } = useToast();
  const [error, setError] = useState<string>();
  return (
    <Modal
      open={answer !== null}
      onClose={() => {
        setError(undefined);
        onClose();
      }}
      title="Delete this answer?"
      description="Forms that ask this question will need a new answer."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Keep it
          </Button>
          <Button
            variant="danger-solid"
            loading={del.isPending}
            onClick={() =>
              answer &&
              del.mutate(answer.id, {
                onSuccess: () => {
                  toast({ kind: "success", title: "Answer deleted" });
                  onClose();
                },
                onError: (e) => setError(copyFor(e, ERRORS)),
              })
            }
          >
            Delete answer
          </Button>
        </>
      }
    >
      {answer && <p className="font-medium">{answer.question}</p>}
      {error && (
        <p role="alert" className="mt-2 text-hint font-medium text-bad">
          {error}
        </p>
      )}
    </Modal>
  );
}
