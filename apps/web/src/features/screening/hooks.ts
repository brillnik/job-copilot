"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";
import type { components } from "@/lib/api/schema";

export type ScreeningAnswer = components["schemas"]["ScreeningAnswerOut"];
export const screeningKey = ["screening-answers"] as const;

export function useScreeningAnswers() {
  return useQuery({
    queryKey: screeningKey,
    queryFn: async () => (await unwrap(api.GET("/screening-answers"))).items,
  });
}

export function useSaveScreeningAnswer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; answer: string; question?: string }) =>
      unwrap(
        api.PUT("/screening-answers/{answer_id}", {
          params: { path: { answer_id: v.id } },
          body: { answer: v.answer, question: v.question ?? null },
        }),
      ),
    onSuccess: (a) =>
      qc.setQueryData<ScreeningAnswer[]>(screeningKey, (old) =>
        old?.map((x) => (x.id === a.id ? a : x)),
      ),
  });
}

export function useDeleteScreeningAnswer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/screening-answers/{answer_id}", {
          params: { path: { answer_id: id } },
        }),
      ),
    onSuccess: (_d, id) =>
      qc.setQueryData<ScreeningAnswer[]>(screeningKey, (old) =>
        old?.filter((x) => x.id !== id),
      ),
  });
}
