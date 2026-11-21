"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { ApiError, toApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { unwrap } from "@/lib/api/unwrap";

export type Board = components["schemas"]["Board"];
export type TrackerCard = components["schemas"]["Card"];
export type CardDetail = components["schemas"]["CardDetail"];
export type Column = TrackerCard["column"];

export const COLUMNS: { id: Column; label: string }[] = [
  { id: "approved", label: "Approved" },
  { id: "applied", label: "Applied" },
  { id: "response", label: "Response" },
  { id: "interview", label: "Interview" },
  { id: "offer", label: "Offer" },
  { id: "rejected", label: "Rejected" },
];
export const columnLabel = (c: Column) =>
  COLUMNS.find((x) => x.id === c)?.label ?? c;

export const boardKey = ["tracker", "board"] as const;
/** Full notes only ever arrive in PATCH responses (there is no GET /tracker/{id}); keep them for the session. */
export const notesKey = ["tracker", "notes"] as const;

export function useBoard() {
  return useQuery({
    queryKey: boardKey,
    queryFn: () => unwrap(api.GET("/tracker")),
  });
}

/** Pure: move a card to `column` at `index` (end when undefined). Counts follow. */
export function moveInBoard(
  board: Board,
  cardId: string,
  column: Column,
  index?: number,
): Board {
  let moved: TrackerCard | undefined;
  const columns = { ...board.columns } as Record<Column, TrackerCard[]>;
  for (const c of COLUMNS) {
    const list = columns[c.id] ?? [];
    const found = list.find((x) => x.id === cardId);
    if (found) {
      moved = found;
      columns[c.id] = list.filter((x) => x.id !== cardId);
    } else columns[c.id] = list;
  }
  if (!moved) return board;
  const target = [...columns[column]];
  const at =
    index === undefined
      ? target.length
      : Math.max(0, Math.min(index, target.length));
  target.splice(at, 0, { ...moved, column });
  columns[column] = target;
  const counts = Object.fromEntries(
    COLUMNS.map((c) => [c.id, columns[c.id].length]),
  ) as Board["stats"]["counts"];
  return { columns, stats: { ...board.stats, counts } };
}

function replaceCard(board: Board, card: TrackerCard): Board {
  const columns = { ...board.columns } as Record<Column, TrackerCard[]>;
  for (const c of COLUMNS) {
    columns[c.id] = (columns[c.id] ?? []).map((x) =>
      x.id === card.id ? card : x,
    );
  }
  return { ...board, columns };
}

async function patchCard(
  card: Pick<TrackerCard, "id" | "rev">,
  body: components["schemas"]["TrackerPatch"],
): Promise<CardDetail> {
  const { data, error, response } = await api.PATCH("/tracker/{card_id}", {
    params: {
      path: { card_id: card.id },
      header: { "if-match": `"${card.rev}"` },
    },
    body,
  });
  if (data) return data;
  throw toApiError(error, response.status);
}

export function findCard(board: Board | undefined, id: string) {
  if (!board) return undefined;
  for (const c of COLUMNS) {
    const f = board.columns[c.id]?.find((x) => x.id === id);
    if (f) return f;
  }
}

/** Optimistic move; a failed PATCH (409 stale_write included) rolls back and reloads. */
export function useMoveCard(onFail: (e: unknown) => void) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ["tracker", "move"],
    mutationFn: (v: { card: TrackerCard; column: Column; position?: number }) =>
      patchCard(v.card, { column: v.column, position: v.position ?? null }),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: boardKey });
      const previous = qc.getQueryData<Board>(boardKey);
      if (previous)
        qc.setQueryData(
          boardKey,
          moveInBoard(previous, v.card.id, v.column, v.position),
        );
      return { previous };
    },
    onError: (e, _v, ctx) => {
      if (ctx?.previous) qc.setQueryData(boardKey, ctx.previous);
      onFail(e);
      void qc.invalidateQueries({ queryKey: boardKey });
    },
    onSuccess: (detail, v) => {
      qc.setQueryData<Board>(boardKey, (b) => (b ? replaceCard(b, detail) : b));
      qc.setQueryData<Record<string, string | null>>(notesKey, (n) => ({
        ...n,
        [v.card.id]: detail.notes,
      }));
    },
    onSettled: () => {
      // Stats (this week, response rate) are server-computed: refresh once the last move lands.
      if (qc.isMutating({ mutationKey: ["tracker", "move"] }) <= 1)
        void qc.invalidateQueries({ queryKey: boardKey });
    },
  });
}

export function useUpdateCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: {
      card: Pick<TrackerCard, "id" | "rev">;
      notes?: string | null;
      applied_at?: string | null;
    }) => {
      const body: components["schemas"]["TrackerPatch"] = {};
      if (v.notes !== undefined) body.notes = v.notes;
      if (v.applied_at !== undefined) body.applied_at = v.applied_at;
      return patchCard(v.card, body);
    },
    onSuccess: (detail) => {
      qc.setQueryData<Board>(boardKey, (b) => (b ? replaceCard(b, detail) : b));
      qc.setQueryData<Record<string, string | null>>(notesKey, (n) => ({
        ...n,
        [detail.id]: detail.notes,
      }));
    },
    onError: (e) => {
      if (e instanceof ApiError && e.isStaleWrite)
        void qc.invalidateQueries({ queryKey: boardKey });
    },
  });
}

export function useRemoveCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await unwrap(
        api.DELETE("/tracker/{card_id}", { params: { path: { card_id: id } } }),
      );
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: boardKey }),
  });
}

export function trackerErrorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "stale_write")
      return "This card was changed somewhere else. The board has been reloaded; try again.";
    return e.message;
  }
  return "Something went wrong. Check your connection and try again.";
}

export const percent = (r: number | null) =>
  r === null ? null : `${Math.round(r * 100)}%`;

/** Is the 120-character notes preview the whole note? (It cuts with an ellipsis.) */
export function previewIsComplete(preview: string | null) {
  return preview === null || (preview.length < 120 && !preview.endsWith("…"));
}
