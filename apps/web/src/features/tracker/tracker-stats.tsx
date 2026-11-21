import { Card } from "@/components/ui/card";
import { COLUMNS, type Board, percent } from "./api";

export function TrackerStats({ stats }: { stats: Board["stats"] }) {
  const total = COLUMNS.reduce((n, c) => n + (stats.counts[c.id] ?? 0), 0);
  const rate = percent(stats.response_rate);
  const items = [
    {
      label: "Applied this week",
      value: String(stats.applied_this_week),
      note: undefined,
    },
    {
      label: "Response rate",
      value: rate ?? "–",
      note: rate === null ? "No applications sent yet" : undefined,
    },
    {
      label: "Avg match score",
      value:
        stats.avg_match_score === null
          ? "–"
          : String(Math.round(stats.avg_match_score)),
      note:
        stats.avg_match_score === null ? "No scored jobs yet" : "out of 100",
    },
    { label: "Tracked", value: String(total), note: "applications" },
  ];
  return (
    <section aria-label="Tracker stats" className="mb-5">
      <dl className="m-0 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {items.map((i) => (
          <Card key={i.label} className="p-3 md:p-4">
            <dt className="text-hint font-medium text-muted">{i.label}</dt>
            <dd className="m-0 mt-1 flex items-baseline gap-1.5">
              <span className="font-mono text-screen font-semibold tabular-nums">
                {i.value}
              </span>
              {i.note && (
                <span className="text-hint text-subtle">{i.note}</span>
              )}
            </dd>
          </Card>
        ))}
      </dl>
      <p className="mt-2 text-hint text-subtle">
        {COLUMNS.map((c) => `${c.label} ${stats.counts[c.id] ?? 0}`).join(
          " · ",
        )}
      </p>
    </section>
  );
}
