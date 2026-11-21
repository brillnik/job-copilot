import { Eyebrow } from "@/components/ui/eyebrow";
import { cn } from "@/lib/cn";

export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
  level = "page",
  className,
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: React.ReactNode;
  /** page = 28/600 (top-level pages), screen = 22/600 (sub-screens). */
  level?: "page" | "screen";
  className?: string;
}) {
  return (
    <header
      className={cn(
        "mb-6 flex flex-wrap items-end justify-between gap-4",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && <Eyebrow className="mb-1">{eyebrow}</Eyebrow>}
        <h1
          className={cn(
            "font-semibold",
            level === "page" ? "text-page" : "text-screen",
          )}
        >
          {title}
        </h1>
        {description && (
          <p className="mt-1 max-w-2xl text-muted">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
