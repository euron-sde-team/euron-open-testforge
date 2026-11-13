"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { GeneratedTest, Generation, GenerateRequest, TestDetail } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { inFlight } from "@/lib/status";

const p = (pid: string) => ({ params: { path: { project_id: pid } } });

export interface TestFilters {
  status?: string;
  kind?: string;
  generation_id?: string;
  unit_id?: string;
}

export function useTests(pid: string, filters: TestFilters = {}) {
  return useQuery<GeneratedTest[]>({
    queryKey: qk.tests(pid, filters),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/tests", {
          params: {
            path: { project_id: pid },
            query: {
              status: filters.status || null,
              kind: filters.kind || null,
              generation_id: filters.generation_id || null,
              unit_id: filters.unit_id || null,
            },
          },
        }),
      ),
    staleTime: STALE.list,
  });
}

export function useTest(pid: string, tid: string) {
  return useQuery<TestDetail>({
    queryKey: qk.test(pid, tid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/tests/{test_id}", { params: { path: { project_id: pid, test_id: tid } } })),
    staleTime: STALE.detail,
  });
}

export function useGenerations(pid: string) {
  return useQuery<Generation[]>({
    queryKey: qk.generations(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/generations", p(pid))),
    staleTime: STALE.list,
  });
}

/** One generation, polled while the model writes. */
export function useGeneration(pid: string, gid: string | null | undefined) {
  return useQuery<Generation>({
    queryKey: qk.generation(pid, gid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/generations/{generation_id}", { params: { path: { project_id: pid, generation_id: gid as string } } })),
    enabled: !!gid,
    staleTime: STALE.live,
    refetchInterval: (q) => (q.state.data && !inFlight(q.state.data.status) ? false : 1200),
  });
}

function invalidateTests(client: ReturnType<typeof useQueryClient>, pid: string) {
  void client.invalidateQueries({ queryKey: qk.testsAll(pid) });
  void client.invalidateQueries({ queryKey: qk.generations(pid) });
  void client.invalidateQueries({ queryKey: qk.overview(pid) });
  void client.invalidateQueries({ queryKey: qk.projects });
}

/** Start a generation; it answers at once (the dialog then polls the generation). */
export function useGenerate(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: GenerateRequest) =>
      unwrap(api.POST("/api/v1/projects/{project_id}/tests/generate", { params: { path: { project_id: pid }, query: { wait: 0 } }, body })),
    onSuccess: () => invalidateTests(client, pid),
  });
}

export function useRefreshTests(pid: string) {
  const client = useQueryClient();
  return () => invalidateTests(client, pid);
}

export function useReviewTest(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: "accepted" | "discarded" | "proposed" }) =>
      unwrap(api.PATCH("/api/v1/projects/{project_id}/tests/{test_id}", { params: { path: { project_id: pid, test_id: id } }, body: { status } })),
    onSuccess: (_d, v) => {
      void client.invalidateQueries({ queryKey: qk.test(pid, v.id) });
      invalidateTests(client, pid);
    },
  });
}

export function useBulkReview(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { ids: string[]; status: "accepted" | "discarded" }) =>
      unwrap(api.POST("/api/v1/projects/{project_id}/tests/review", { ...p(pid), body })),
    onSuccess: () => invalidateTests(client, pid),
  });
}

export function useRegenerate(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (tid: string) =>
      unwrap(api.POST("/api/v1/projects/{project_id}/tests/{test_id}/regenerate", { params: { path: { project_id: pid, test_id: tid }, query: { wait: 0 } } })),
    onSuccess: () => invalidateTests(client, pid),
  });
}
