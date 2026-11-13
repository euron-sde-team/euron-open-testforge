"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Pull, PullDetail } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { inFlight } from "@/lib/status";

export function usePulls(pid: string) {
  return useQuery<Pull[]>({
    queryKey: qk.pulls(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/pulls", { params: { path: { project_id: pid } } })),
    staleTime: STALE.list,
    refetchInterval: (q) => (q.state.data?.some((r) => inFlight(r.status)) ? 1500 : false),
  });
}

export function usePull(pid: string, prid: string) {
  return useQuery<PullDetail>({
    queryKey: qk.pull(pid, prid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/pulls/{pull_id}", { params: { path: { project_id: pid, pull_id: prid } } })),
    staleTime: STALE.detail,
    refetchInterval: (q) => (q.state.data && !inFlight(q.state.data.status) ? false : 1500),
  });
}

export function useImportPull(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { number: number; repo?: string | null }) =>
      unwrap(api.POST("/api/v1/projects/{project_id}/pulls", { params: { path: { project_id: pid }, query: { wait: 0 } }, body })),
    onSuccess: (pull) => {
      client.setQueryData(qk.pull(pid, pull.id), pull);
      void client.invalidateQueries({ queryKey: qk.pulls(pid) });
    },
  });
}
