import { CheckChip, Chip, SourceChip } from "@/components/ui/chip";
import type { Must } from "./types";

const short = (id: string) => (id.length > 8 ? id.slice(0, 8) : id);

/**
 * Must-have coverage. `have` chips cite the profile bullet that proves them:
 * when the approved profile contains that bullet its text shows in a tooltip,
 * otherwise only the bullet id is shown.
 */
export function MustChips({
  musts,
  bulletTexts,
}: {
  musts: Must[];
  bulletTexts?: ReadonlyMap<string, string>;
}) {
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Must-have skills">
      {musts.map((m) => {
        const bullet = m.evidence_bullet_id;
        const text = bullet ? bulletTexts?.get(bullet) : undefined;
        return (
          <li key={m.skill} className="inline-flex items-center gap-1">
            {m.status === "unknown" ? (
              <Chip>
                <span className="sr-only">Not assessed: </span>
                {m.skill}
              </Chip>
            ) : (
              <CheckChip state={m.status}>{m.skill}</CheckChip>
            )}
            {m.status === "have" &&
              bullet &&
              (text ? (
                <SourceChip id={bullet} label={short(bullet)} original={text} />
              ) : (
                <span
                  className="font-mono text-hint text-subtle"
                  title="Evidence bullet id"
                >
                  <span className="sr-only">Evidence bullet </span>
                  {short(bullet)}
                </span>
              ))}
          </li>
        );
      })}
    </ul>
  );
}
