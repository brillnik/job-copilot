"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";

export const reviewCountKey = ["runs", "in_review", "count"] as const;
const LIMIT = 50;

// There is no count endpoint: derive it from GET /runs?status=in_review.
// `more` is true when there are further pages (render "50+").
export function useReviewCount() {
  return useQuery({
    queryKey: reviewCountKey,
    queryFn: async () => {
      const page = await unwrap(
        api.GET("/runs", {
          params: { query: { status: "in_review", limit: LIMIT } },
        }),
      );
      return { count: page.items.length, more: page.next_cursor !== null };
    },
    refetchInterval: 60_000,
  });
}
