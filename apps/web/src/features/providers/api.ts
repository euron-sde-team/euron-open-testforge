"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Provider, ProviderCreate, ProviderUpdate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

const p = (pid: string) => ({ params: { path: { project_id: pid } } });
const one = (pid: string, id: string) => ({ params: { path: { project_id: pid, provider_id: id } } });

export function useProviders(pid: string) {
  return useQuery<Provider[]>({
    queryKey: qk.providers(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/providers", p(pid))),
    staleTime: STALE.config,
  });
}

export function useCreateProvider(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderCreate) => unwrap(api.POST("/api/v1/projects/{project_id}/providers", { ...p(pid), body })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.providers(pid) }),
  });
}

export function useUpdateProvider(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ProviderUpdate }) =>
      unwrap(api.PATCH("/api/v1/projects/{project_id}/providers/{provider_id}", { ...one(pid, id), body })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.providers(pid) }),
  });
}

export function useDeleteProvider(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/projects/{project_id}/providers/{provider_id}", one(pid, id))),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.providers(pid) }),
  });
}

export function useTestProvider(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/api/v1/projects/{project_id}/providers/{provider_id}/test", one(pid, id))),
    onSettled: () => client.invalidateQueries({ queryKey: qk.providers(pid) }),
  });
}
