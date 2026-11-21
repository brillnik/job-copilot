"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { MetricChip, StatusChip } from "@/components/ui/chip";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { TrackerIcon } from "@/components/ui/icons";
import { KanbanCard } from "@/components/ui/kanban-card";
import { Skeleton, SkeletonGroup } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { errorMessage } from "@/lib/api/errors";
import {
  COLUMNS,
  type Column,
  type TrackerCard,
  columnLabel,
  findCard,
  notesKey,
  trackerErrorMessage,
  useBoard,
  useMoveCard,
} from "./api";
import { CardDialog } from "./card-dialog";
import { TrackerStats } from "./tracker-stats";

const COLUMN_LABELS = COLUMNS.map((c) => c.label);

function appliedText(iso: string | null) {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  return days <= 0 ? "Applied today" : `Applied ${days}d ago`;
}

export function TrackerBoard() {
  const { toast } = useToast();
  const q = useBoard();
  const notes = useQuery<Record<string, string | null>>({
    queryKey: notesKey,
    queryFn: () => ({}),
    staleTime: Infinity,
    gcTime: Infinity,
    initialData: {},
  });
  const [announce, setAnnounce] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<Column | null>(null);

  const move = useMoveCard((e) => {
    const msg = trackerErrorMessage(e);
    setAnnounce(`Move failed and was undone. ${msg}`);
    toast({ kind: "error", title: "Couldn't move the card", description: msg });
  });

  function moveCard(card: TrackerCard, column: Column, position?: number) {
    if (card.column === column && position === undefined) return;
    move.mutate({ card, column, position });
    setAnnounce(`${card.title ?? "Card"} moved to ${columnLabel(column)}.`);
  }

  if (q.isPending)
    return (
      <>
        <PageHeader
          title="Tracker"
          description="Follow every application from approved to offer."
        />
        <SkeletonGroup label="Loading tracker">
          <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-20 rounded-card" />
            ))}
          </div>
          <div className="flex gap-3 overflow-hidden">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-64 w-64 shrink-0 rounded-card" />
            ))}
          </div>
        </SkeletonGroup>
      </>
    );
  if (q.isError)
    return (
      <>
        <PageHeader title="Tracker" />
        <ErrorState
          title="Couldn't load the tracker"
          message={errorMessage(q.error)}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
        />
      </>
    );

  const board = q.data;
  const total = COLUMNS.reduce(
    (n, c) => n + (board.columns[c.id]?.length ?? 0),
    0,
  );
  const open = openId ? findCard(board, openId) : undefined;

  function onDrop(e: React.DragEvent<HTMLUListElement>, column: Column) {
    e.preventDefault();
    setOverCol(null);
    const id = e.dataTransfer.getData("text/plain");
    const card = findCard(board, id);
    if (!card) return;
    // Index = number of other cards whose midpoint is above the pointer.
    const items = Array.from(e.currentTarget.children).filter(
      (el): el is HTMLElement =>
        el instanceof HTMLElement &&
        el.dataset.cardId !== undefined &&
        el.dataset.cardId !== id,
    );
    let index = 0;
    for (const el of items) {
      const r = el.getBoundingClientRect();
      if (e.clientY > r.top + r.height / 2) index++;
    }
    if (
      card.column === column &&
      (board.columns[column] ?? []).findIndex((c) => c.id === id) === index
    )
      return; // dropped where it already is
    moveCard(card, column, index);
  }

  return (
    <>
      <PageHeader
        title="Tracker"
        description="Follow every application from approved to offer."
      />
      <TrackerStats stats={board.stats} />
      <p role="status" aria-live="polite" className="sr-only">
        {announce}
      </p>
      {total === 0 && (
        <EmptyState
          className="mb-5"
          icon={<TrackerIcon />}
          title="No applications tracked"
          description="Approved applications will appear here as cards you can move between stages."
        />
      )}
      <div
        role="region"
        aria-label="Application board"
        // axe (scrollable-region-focusable): a scrollable region must be keyboard reachable.
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-3 md:mx-0 md:px-0 lg:grid lg:grid-cols-6 lg:overflow-visible"
      >
        {COLUMNS.map((col, colIndex) => {
          const cards = board.columns[col.id] ?? [];
          return (
            <section
              key={col.id}
              aria-labelledby={`col-${col.id}`}
              className={cn(
                "flex w-[260px] shrink-0 snap-start flex-col gap-2 rounded-card-mobile border bg-surface-2 p-2.5 md:rounded-card lg:w-auto",
                overCol === col.id
                  ? "border-accent ring-2 ring-accent"
                  : "border-border",
              )}
            >
              <h2
                id={`col-${col.id}`}
                className="flex items-center justify-between px-1 text-body font-semibold"
              >
                {col.label}
                <MetricChip aria-label={`${cards.length} cards`}>
                  {cards.length}
                </MetricChip>
              </h2>
              <ul
                aria-label={`${col.label} cards`}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  setOverCol(col.id);
                }}
                onDragLeave={(e) => {
                  if (!e.currentTarget.contains(e.relatedTarget as Node))
                    setOverCol(null);
                }}
                onDrop={(e) => onDrop(e, col.id)}
                className="m-0 flex min-h-20 list-none flex-col gap-2 p-0"
              >
                {cards.length === 0 && (
                  <li className="px-1 py-3 text-hint text-subtle">
                    Nothing here. Drop a card to move it.
                  </li>
                )}
                {cards.map((c) => (
                  <KanbanCard
                    key={c.id}
                    title={c.title ?? "Untitled job"}
                    subtitle={c.company ?? undefined}
                    columnLabel={col.label}
                    columnIndex={colIndex}
                    columnCount={COLUMNS.length}
                    columnLabels={COLUMN_LABELS}
                    dragData={c.id}
                    onMove={(i) => moveCard(c, COLUMNS[i].id)}
                    meta={
                      <>
                        {c.score !== null && (
                          <MetricChip>Match {c.score}</MetricChip>
                        )}
                        {appliedText(c.applied_at) && (
                          <StatusChip>{appliedText(c.applied_at)}</StatusChip>
                        )}
                        {c.notes_preview && (
                          <span className="line-clamp-2 basis-full text-hint text-muted">
                            {c.notes_preview}
                          </span>
                        )}
                      </>
                    }
                    actions={
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setOpenId(c.id)}
                      >
                        Details
                        <span className="sr-only">
                          {" "}
                          for {c.title ?? "this job"}
                        </span>
                      </Button>
                    }
                  />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      {open && (
        <CardDialog
          key={open.id}
          card={open}
          knownNotes={notes.data[open.id]}
          onClose={() => setOpenId(null)}
          onMove={(column) => moveCard(open, column)}
        />
      )}
    </>
  );
}
