"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";
import type { components } from "@/lib/api/schema";

export type PairCode = components["schemas"]["PairCodeOut"];
export type DeviceToken = components["schemas"]["TokenOut"];
export const tokensKey = ["extension", "tokens"] as const;

export function useDevices() {
  return useQuery({
    queryKey: tokensKey,
    queryFn: () => unwrap(api.GET("/extension/tokens")),
  });
}

export function useCreatePairCode() {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/extension/pair-code")),
  });
}

export function useRevokeDevice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/extension/tokens/{token_id}", {
          params: { path: { token_id: id } },
        }),
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: tokensKey }),
  });
}
