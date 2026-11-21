"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextareaField } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import type { Answer, PendingQuestion } from "./types";

type Choice = "yes" | "no" | "";

/**
 * The agent's questions about skills it could not verify. One submit sends all
 * answers (POST /runs/{id}/answer takes a list). Answers survive a failed send.
 */
export function QuestionCard({
  questions,
  onSubmit,
}: {
  questions: PendingQuestion[];
  onSubmit: (answers: Answer[]) => Promise<void>;
}) {
  const [choice, setChoice] = useState<Record<string, Choice>>({});
  const [detail, setDetail] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const unanswered = questions.filter((q) => !choice[q.skill]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (unanswered.length) {
      setError("Answer every question to continue.");
      return;
    }
    setBusy(true);
    setError(undefined);
    try {
      await onSubmit(
        questions.map((q) => {
          const d = detail[q.skill]?.trim();
          return {
            skill: q.skill,
            answer: choice[q.skill] as "yes" | "no",
            ...(choice[q.skill] === "yes" && d ? { detail: d } : {}),
          };
        }),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't send your answers.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card as="section" aria-labelledby="questions-h" className="border-accent">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div>
          <h3 id="questions-h" className="text-section font-semibold">
            The agent needs your input
          </h3>
          <p className="text-muted">
            Only say yes to skills you can back up. Your answers are used to
            write the resume.
          </p>
        </div>
        {questions.map((q) => (
          <fieldset key={q.skill} className="flex flex-col gap-2">
            <legend className="mb-1 font-medium">
              {q.prompt ?? `Do you have hands-on experience with ${q.skill}?`}
            </legend>
            <Segmented<Choice>
              label={`Answer for ${q.skill}`}
              options={[
                { value: "yes", label: "Yes" },
                { value: "no", label: "No" },
              ]}
              value={choice[q.skill] ?? ""}
              onChange={(v) => setChoice((c) => ({ ...c, [q.skill]: v }))}
              className="self-start"
            />
            {choice[q.skill] === "yes" && (
              <TextareaField
                label={`Details about ${q.skill} (optional)`}
                hint="Where did you use it? A project or role helps."
                rows={2}
                maxLength={1000}
                value={detail[q.skill] ?? ""}
                onChange={(e) =>
                  setDetail((d) => ({ ...d, [q.skill]: e.target.value }))
                }
              />
            )}
          </fieldset>
        ))}
        {error && (
          <p role="alert" className="text-hint font-medium text-bad">
            {error}
          </p>
        )}
        <div>
          <Button type="submit" variant="primary" loading={busy}>
            Send answers
          </Button>
        </div>
      </form>
    </Card>
  );
}
