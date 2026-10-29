"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";

export const meKey = ["me"] as const;

// Client-side fetch of the signed-in user via the /api proxy.
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/me");
      if (error) throw error;
      return data;
    },
  });
}
