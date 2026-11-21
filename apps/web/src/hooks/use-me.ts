"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";

export const meKey = ["me"] as const;

// Client-side fetch of the signed-in user via the /api proxy.
export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: () => unwrap(api.GET("/me")),
  });
}
