import { Logo } from "@/components/brand/logo";
import { Chip } from "@/components/ui/chip";

const STEPS = ["Sign in", "Upload", "Review", "Preferences"];

export function SetupHeader({ current }: { current: number }) {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-border bg-surface px-4 py-4 sm:px-8 sm:py-5">
      <div className="flex items-center gap-2.5 text-[15px] font-semibold">
        <Logo />
        <span>Job Copilot</span>
      </div>
      <ol aria-label="Setup progress" className="flex flex-wrap items-center gap-1.5">
        {STEPS.map((name, i) => (
          <li key={name} className="flex items-center gap-1.5">
            <Chip current={i === current} aria-current={i === current ? "step" : undefined}>
              {i + 1} · {name}
            </Chip>
            {i < STEPS.length - 1 && (
              <span className="text-subtle" aria-hidden="true">
                —
              </span>
            )}
          </li>
        ))}
      </ol>
    </header>
  );
}
