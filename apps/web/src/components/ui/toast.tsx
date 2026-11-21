"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";
import { AlertIcon, CheckIcon, InfoIcon, XIcon } from "./icons";

export type ToastKind = "info" | "success" | "error";
export type ToastOptions = {
  title: string;
  description?: string;
  kind?: ToastKind;
  action?: { label: string; onClick: () => void };
  /** ms; 0 keeps it until dismissed. Defaults: 5000, errors 8000. */
  duration?: number;
};

const icons = { info: InfoIcon, success: CheckIcon, error: AlertIcon } as const;
const kindLabel = { info: "Notice", success: "Done", error: "Error" } as const;

/** Presentational toast (also used directly in Storybook). */
export function Toast({
  kind = "info",
  title,
  description,
  action,
  onDismiss,
  className,
}: ToastOptions & { onDismiss?: () => void; className?: string }) {
  const Icon = icons[kind];
  return (
    <div
      role={kind === "error" ? "alert" : "status"}
      className={cn(
        "flex w-full items-start gap-3 rounded-card border border-border-strong bg-surface p-3 pl-4 text-text shadow-lg md:w-96",
        className,
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          kind === "error" ? "text-text" : "text-accent-text",
        )}
      />
      <div className="min-w-0 flex-1">
        <p className="text-body font-semibold">
          <span className="sr-only">{kindLabel[kind]}: </span>
          {title}
        </p>
        {description && <p className="text-hint text-muted">{description}</p>}
        {action && (
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 -ml-3 text-accent-text"
            onClick={action.onClick}
          >
            {action.label}
          </Button>
        )}
      </div>
      {onDismiss && (
        <Button
          iconOnly
          variant="ghost"
          size="sm"
          aria-label="Dismiss notification"
          onClick={onDismiss}
        >
          <XIcon />
        </Button>
      )}
    </div>
  );
}

type Item = ToastOptions & { id: number };
type Ctx = {
  toast: (o: ToastOptions) => number;
  dismiss: (id: number) => void;
};
const ToastContext = createContext<Ctx | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current.get(id));
    timers.current.delete(id);
    setItems((xs) => xs.filter((x) => x.id !== id));
  }, []);

  const toast = useCallback(
    (o: ToastOptions) => {
      const id = nextId.current++;
      setItems((xs) => [...xs.slice(-3), { ...o, id }]);
      const ms = o.duration ?? (o.kind === "error" ? 8000 : 5000);
      if (ms > 0)
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), ms),
        );
      return id;
    },
    [dismiss],
  );

  useEffect(() => {
    const t = timers.current;
    return () => t.forEach(clearTimeout);
  }, []);

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss]);
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        role="region"
        aria-label="Notifications"
        className="pointer-events-none fixed inset-x-4 bottom-20 z-50 flex flex-col items-center gap-2 md:inset-x-auto md:right-4 md:bottom-4 md:items-end"
      >
        {items.map((t) => (
          <div key={t.id} className="pointer-events-auto w-full md:w-auto">
            <Toast {...t} onDismiss={() => dismiss(t.id)} />
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
