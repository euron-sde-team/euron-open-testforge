"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Coverage, ProjectCoverage, Run, RunCreate, RunDetail } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { inFlight } from "@/lib/status";

export function useRuns(pid: string, status?: string) {
  return useQuery<Run[]>({
    queryKey: qk.runs(pid, { status }),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/runs", { params: { path: { project_id: pid }, query: { status: status || null, limit: 100 } } })),
    staleTime: STALE.list,
    refetchInterval: (q) => (q.state.data?.some((r) => inFlight(r.status)) ? 2000 : false),
  });
}

/** One run with its test cases, polled until the sandbox reports back. */
export function useRun(pid: string, rid: string) {
  const client = useQueryClient();
  return useQuery<RunDetail>({
    queryKey: qk.run(pid, rid),
    queryFn: async () => {
      const run = await unwrap(api.GET("/api/v1/projects/{project_id}/runs/{run_id}", { params: { path: { project_id: pid, run_id: rid } } }));
      if (!inFlight(run.status)) {
        void client.invalidateQueries({ queryKey: qk.runsAll(pid) });
        void client.invalidateQueries({ queryKey: qk.overview(pid) });
      }
      return run;
    },
    staleTime: STALE.detail,
    refetchInterval: (q) => (q.state.data && !inFlight(q.state.data.status) ? false : 1500),
  });
}

export function useStartRun(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: RunCreate) => unwrap(api.POST("/api/v1/projects/{project_id}/runs", { params: { path: { project_id: pid }, query: { wait: 0 } }, body })),
    onSuccess: (run) => {
      client.setQueryData(qk.run(pid, run.id), run);
      void client.invalidateQueries({ queryKey: qk.runsAll(pid) });
      void client.invalidateQueries({ queryKey: qk.overview(pid) });
    },
  });
}

/** Ask the project's model for a narrative on one failure (the structured explanation is always there). */
export function useExplainWithModel(pid: string) {
  return useMutation({
    mutationFn: (body: { run_id: string; case_id: string }) =>
      unwrap(api.POST("/api/v1/projects/{project_id}/bugs/analyze", { params: { path: { project_id: pid } }, body: { ...body, use_model: true } })),
  });
}

export function useRunCoverage(pid: string, rid: string | null | undefined, enabled = true) {
  return useQuery<Coverage>({
    queryKey: qk.runCoverage(pid, rid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/runs/{run_id}/coverage", { params: { path: { project_id: pid, run_id: rid as string } } })),
    enabled: enabled && !!rid,
    staleTime: STALE.static,
    retry: false,
  });
}

export function useProjectCoverage(pid: string) {
  return useQuery<ProjectCoverage>({
    queryKey: qk.coverage(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/coverage", { params: { path: { project_id: pid } } })),
    staleTime: STALE.list,
  });
}
