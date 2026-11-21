"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";

export const screeningAnswersKey = ["screening-answers"] as const;

/** The remembered-answer bank (GET /screening-answers). */
export function useScreeningAnswers() {
  return useQuery({
    queryKey: screeningAnswersKey,
    queryFn: async () => (await unwrap(api.GET("/screening-answers"))).items,
  });
}
