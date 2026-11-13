"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Spec } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useSpecs(pid: string) {
  return useQuery<Spec[]>({
    queryKey: qk.specs(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/specs", { params: { path: { project_id: pid } } })),
    staleTime: STALE.list,
  });
}

export function useSpec(pid: string, sid: string) {
  return useQuery<Spec>({
    queryKey: qk.spec(pid, sid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/specs/{spec_id}", { params: { path: { project_id: pid, spec_id: sid } } })),
    staleTime: STALE.static,
  });
}

export function useImportSpec(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (document: string) => unwrap(api.POST("/api/v1/projects/{project_id}/specs", { params: { path: { project_id: pid } }, body: { document } })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.specs(pid) }),
  });
}
