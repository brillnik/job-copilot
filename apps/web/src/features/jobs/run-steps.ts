import type { Step } from "@/components/ui/stepper";
import type { RunStatus } from "./types";

// Step names the backend pipeline emits (agent/pipeline.py). Anything else is
// shown generically with its name humanised.
export const KNOWN_STEPS: ReadonlyArray<readonly [string, string]> = [
  ["load_context", "Read your profile and the posting"],
  ["rank_items", "Pick your most relevant experience"],
  ["plan", "Plan the resume"],
  ["write_draft", "Write the draft"],
  ["fact_check", "Fact-check every claim"],
  ["coverage_and_render", "Check coverage and render the PDF"],
];
const LABELS = new Map(KNOWN_STEPS);
const ITERATED = new Set(["write_draft", "fact_check", "coverage_and_render"]);

export function humanizeStep(name: string) {
  const t = name.replace(/[_-]+/g, " ").trim();
  return t ? t[0].toUpperCase() + t.slice(1) : "Working";
}

export type StepProgress = {
  /** Step names in the order they were first reached. */
  order: string[];
  /** The step the run is on now (last step event). */
  current: string | null;
  iterations: Record<string, number>;
};

export const emptyProgress: StepProgress = {
  order: [],
  current: null,
  iterations: {},
};

export function reduceStep(
  p: StepProgress,
  step: string,
  iteration?: number,
): StepProgress {
  return {
    order: p.order.includes(step) ? p.order : [...p.order, step],
    current: step,
    iterations:
      iteration === undefined
        ? p.iterations
        : { ...p.iterations, [step]: iteration },
  };
}

/** Run status + step events -> Stepper steps. */
export function buildRunSteps(
  status: RunStatus,
  progress: StepProgress,
  currentStep?: string | null,
): Step[] {
  const finished =
    status === "in_review" || status === "approved" || status === "rejected";
  const stopped = status === "needs_attention" || status === "cancelled";
  let { order, current } = progress;
  // Runs resumed after a reload may only know the server's current_step.
  if (currentStep && !order.includes(currentStep)) {
    order = [...order, currentStep];
    current ??= currentStep;
  }
  current ??= currentStep ?? null;

  const steps: Step[] = [
    {
      label: "Waiting in the queue",
      state: status === "queued" ? "running" : "done",
    },
  ];
  const reached = status === "queued" ? [] : order;
  const curIdx = current ? reached.indexOf(current) : -1;
  reached.forEach((name, i) => {
    const iter = progress.iterations[name];
    const detail = ITERATED.has(name) && iter ? `Iteration ${iter}` : undefined;
    let state: Step["state"];
    if (finished) state = "done";
    else if (i < curIdx) state = "done";
    else if (i === curIdx) {
      state = stopped
        ? "queued"
        : status === "waiting_for_user"
          ? "waiting"
          : "running";
    } else state = "queued";
    steps.push({
      label: LABELS.get(name) ?? humanizeStep(name),
      state,
      detail: i === curIdx && stopped ? "Stopped" : detail,
    });
  });
  if (!finished && !stopped) {
    for (const [name, label] of KNOWN_STEPS) {
      if (!reached.includes(name)) steps.push({ label, state: "queued" });
    }
  }
  return steps;
}
