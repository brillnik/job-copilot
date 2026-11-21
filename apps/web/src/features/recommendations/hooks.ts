"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";
import type { components } from "@/lib/api/schema";

export type Recommendation = components["schemas"]["RecommendationOut"];

export const recommendationsKey = ["recommendations"] as const;

export function useRecommendations() {
  return useQuery({
    queryKey: recommendationsKey,
    queryFn: async () => (await unwrap(api.GET("/recommendations"))).items,
  });
}

function replace(items: Recommendation[] | undefined, next: Recommendation) {
  return items?.map((r) => (r.id === next.id ? next : r));
}

export function useSaveRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/recommendations/{rec_id}/save", {
          params: { path: { rec_id: id } },
        }),
      ),
    onSuccess: (rec) =>
      qc.setQueryData<Recommendation[]>(recommendationsKey, (old) =>
        replace(old, rec),
      ),
  });
}

export function useDismissRecommendation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; reason?: string }) =>
      unwrap(
        api.POST("/recommendations/{rec_id}/dismiss", {
          params: { path: { rec_id: v.id } },
          body: { reason: v.reason?.trim() || null },
        }),
      ),
    // Dismissed recommendations are hidden by the server, so drop it locally too.
    onSuccess: (rec) =>
      qc.setQueryData<Recommendation[]>(recommendationsKey, (old) =>
        old?.filter((r) => r.id !== rec.id),
      ),
  });
}
