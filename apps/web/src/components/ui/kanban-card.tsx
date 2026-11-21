"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import { GripIcon } from "./icons";

/**
 * Tracker card. Mouse/touch: HTML5 drag (set `dragData` to the card id).
 * Keyboard: focus the card, press Space/Enter to pick up, Left/Right to move
 * between columns, Space/Enter to drop, Escape to cancel. Moves are announced
 * through a polite live region.
 */
export function KanbanCard({
  title,
  subtitle,
  meta,
  columnLabel,
  columnIndex,
  columnCount,
  columnLabels,
  onMove,
  dragData,
  actions,
  className,
}: {
  title: string;
  subtitle?: string;
  meta?: React.ReactNode;
  columnLabel: string;
  columnIndex: number;
  columnCount: number;
  /** Optional names for announcements ("Moved to Interview"). */
  columnLabels?: string[];
  /** Called on drop with the target column index. */
  onMove?: (toIndex: number) => void;
  dragData?: string;
  /** Extra controls (e.g. an "Edit notes" button), rendered beside the card, not inside the draggable. */
  actions?: React.ReactNode;
  className?: string;
}) {
  const [grabbed, setGrabbed] = useState(false);
  const [target, setTarget] = useState(columnIndex);
  const [dragging, setDragging] = useState(false);
  const [announce, setAnnounce] = useState("");
  const name = (i: number) => columnLabels?.[i] ?? `column ${i + 1}`;

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.target !== e.currentTarget) return;
    if (!grabbed) {
      if (e.key === " " || e.key === "Enter") {
        e.preventDefault();
        setGrabbed(true);
        setTarget(columnIndex);
        setAnnounce(
          `Picked up ${title}. Use left and right arrow keys to choose a column, space to drop, escape to cancel.`,
        );
      }
      return;
    }
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const next = Math.max(
        0,
        Math.min(columnCount - 1, target + (e.key === "ArrowRight" ? 1 : -1)),
      );
      setTarget(next);
      setAnnounce(`${name(next)}, position ${next + 1} of ${columnCount}.`);
    } else if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      setGrabbed(false);
      if (target !== columnIndex) {
        onMove?.(target);
        setAnnounce(`${title} moved to ${name(target)}.`);
      } else setAnnounce(`${title} dropped in ${columnLabel}, no change.`);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setGrabbed(false);
      setAnnounce("Move cancelled.");
    }
  }

  return (
    <li data-card-id={dragData} className={cn("list-none", className)}>
      <div
        role="button"
        tabIndex={0}
        draggable
        aria-roledescription="draggable card"
        aria-pressed={grabbed}
        aria-label={`${title}${subtitle ? `, ${subtitle}` : ""}. In ${columnLabel}. Press space to move.`}
        onKeyDown={onKeyDown}
        onBlur={() => setGrabbed(false)}
        onDragStart={(e) => {
          setDragging(true);
          e.dataTransfer.setData("text/plain", dragData ?? title);
          e.dataTransfer.effectAllowed = "move";
        }}
        onDragEnd={() => setDragging(false)}
        className={cn(
          "flex cursor-grab gap-2 rounded-card-mobile border bg-surface p-3 active:cursor-grabbing md:rounded-card",
          grabbed ? "border-accent ring-2 ring-accent" : "border-border",
          dragging && "opacity-50",
        )}
      >
        <GripIcon className="mt-1 shrink-0 text-subtle" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-body font-semibold">{title}</p>
          {subtitle && (
            <p className="truncate text-hint text-muted">{subtitle}</p>
          )}
          {meta && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {meta}
            </div>
          )}
          {grabbed && (
            <p className="mt-2 text-hint font-medium text-accent-text">
              Moving to: {name(target)} ({target + 1}/{columnCount})
            </p>
          )}
        </div>
      </div>
      {actions && <div className="mt-1.5 flex flex-wrap gap-1.5">{actions}</div>}
      <span className="sr-only" aria-live="polite">
        {announce}
      </span>
    </li>
  );
}
