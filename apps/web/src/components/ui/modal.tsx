"use client";

import { useEffect, useId, useRef } from "react";
import { cn } from "@/lib/cn";
import { Button } from "./button";
import { XIcon } from "./icons";

type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  /** "sheet" docks to the bottom edge on mobile (< md) and is a centred dialog on desktop. */
  variant?: "dialog" | "sheet";
};

/**
 * Built on the native <dialog>.showModal(): the rest of the page becomes inert
 * (focus is trapped inside), Escape closes, and focus returns to the opener.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  variant = "dialog",
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    // Escape is handled natively by <dialog>; the click handler only adds backdrop-click-to-close.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // backdrop click
      }}
      className={cn(
        "fixed inset-0 m-auto w-[min(32rem,calc(100%-2rem))] max-w-none overflow-visible border border-border bg-surface p-0 text-text shadow-2xl backdrop:bg-black/50",
        "rounded-card",
        variant === "sheet" &&
          "max-md:mb-0 max-md:w-full max-md:rounded-t-card-mobile max-md:rounded-b-none max-md:border-x-0 max-md:border-b-0",
      )}
    >
      <div className="flex max-h-[85dvh] flex-col">
        <div className="flex items-start justify-between gap-4 border-b border-border p-4 md:px-5">
          <div>
            <h2 id={titleId} className="text-section font-semibold">
              {title}
            </h2>
            {description && (
              <p id={descId} className="mt-1 text-muted">
                {description}
              </p>
            )}
          </div>
          <Button
            iconOnly
            variant="ghost"
            size="sm"
            aria-label="Close"
            onClick={onClose}
          >
            <XIcon />
          </Button>
        </div>
        <div className="overflow-y-auto p-4 md:px-5">{children}</div>
        {footer && (
          <div className="flex flex-wrap justify-end gap-2 border-t border-border p-4 md:px-5">
            {footer}
          </div>
        )}
      </div>
    </dialog>
  );
}

export function BottomSheet(props: Omit<ModalProps, "variant">) {
  return <Modal {...props} variant="sheet" />;
}
