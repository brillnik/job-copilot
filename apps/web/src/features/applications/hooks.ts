"use client";

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api/browser";
import { unwrap } from "@/lib/api/unwrap";
import type { components } from "@/lib/api/schema";
import { ACTIVE, type ApplicationStatus } from "./status";

export type Application = components["schemas"]["ApplicationOut"];
export type FieldAnswer = components["schemas"]["FieldAnswer"];

export const applicationsKey = ["applications"] as const;
export const applicationKey = (id: string) =>
  ["applications", "detail", id] as const;

export function useApplications(status: ApplicationStatus | "") {
  return useInfiniteQuery({
    queryKey: [...applicationsKey, "list", status],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/applications", {
          params: {
            query: {
              status: status || undefined,
              cursor: pageParam,
              limit: 20,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}

export function useApplication(id: string) {
  return useQuery({
    queryKey: applicationKey(id),
    queryFn: () =>
      unwrap(
        api.GET("/applications/{application_id}", {
          params: { path: { application_id: id } },
        }),
      ),
    // Queued and running applications change on their own: poll gently.
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && (s === "queued" || s === "running") ? 5000 : false;
    },
  });
}

function useStore(id: string) {
  const qc = useQueryClient();
  return (app: Application) => {
    qc.setQueryData(applicationKey(id), app);
    void qc.invalidateQueries({ queryKey: [...applicationsKey, "list"] });
  };
}

export function useAnswerApplication(id: string) {
  const store = useStore(id);
  return useMutation({
    mutationFn: (answers: FieldAnswer[]) =>
      unwrap(
        api.POST("/applications/{application_id}/answer", {
          params: { path: { application_id: id } },
          body: { answers },
        }),
      ),
    onSuccess: store,
  });
}

export function useCancelApplication(id: string) {
  const store = useStore(id);
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/applications/{application_id}/cancel", {
          params: { path: { application_id: id } },
        }),
      ),
    onSuccess: store,
  });
}

/** Manual apply for an approved run. Repeating the call returns the existing application. */
export function useApplyRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) =>
      unwrap(
        api.POST("/runs/{run_id}/apply", {
          params: { path: { run_id: runId } },
        }),
      ),
    onSuccess: (app) => {
      qc.setQueryData(applicationKey(app.id), app);
      void qc.invalidateQueries({ queryKey: [...applicationsKey, "list"] });
    },
  });
}

export function isActive(s: ApplicationStatus) {
  return ACTIVE.includes(s);
}
