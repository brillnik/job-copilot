import { cn } from "@/lib/cn";

export function EmptyState({
  title,
  description,
  action,
  icon,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-card border border-dashed border-border-strong bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      {icon && (
        <div className="grid size-12 place-items-center rounded-full bg-accent-soft text-accent-text">
          {icon}
        </div>
      )}
      <h2 className="text-section font-semibold">{title}</h2>
      {description && <p className="max-w-md text-muted">{description}</p>}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
