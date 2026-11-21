import { cn } from "@/lib/cn";
import { Button } from "./button";
import { AlertIcon } from "./icons";

export function ErrorState({
  title = "Something went wrong",
  message,
  onRetry,
  retrying,
  className,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center gap-3 rounded-card border border-border bg-surface px-6 py-12 text-center",
        className,
      )}
    >
      <div className="grid size-12 place-items-center rounded-full bg-bad-soft text-bad">
        <AlertIcon className="size-6" />
      </div>
      <h2 className="text-section font-semibold">{title}</h2>
      {message && <p className="max-w-md text-muted">{message}</p>}
      {onRetry && (
        <Button onClick={onRetry} loading={retrying} className="mt-1">
          Try again
        </Button>
      )}
    </div>
  );
}
