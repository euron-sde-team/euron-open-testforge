"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, rawJson, unwrap } from "@/lib/api/client";
import type { Import } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";
import { inFlight } from "@/lib/status";

const p = (pid: string) => ({ params: { path: { project_id: pid } } });

export function useImports(pid: string) {
  return useQuery<Import[]>({
    queryKey: qk.imports(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/imports", p(pid))),
    staleTime: STALE.list,
    refetchInterval: (q) => (q.state.data?.some((i) => inFlight(i.status)) ? 1500 : false),
  });
}

/** One import, polled while it downloads and is analyzed. */
export function useImport(pid: string, iid: string | null | undefined) {
  return useQuery<Import>({
    queryKey: qk.import(pid, iid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/imports/{import_id}", { params: { path: { project_id: pid, import_id: iid as string } } })),
    enabled: !!iid,
    staleTime: STALE.live,
    refetchInterval: (q) => (q.state.data && !inFlight(q.state.data.status) ? false : 1200),
  });
}

/** Everything that depends on which code is current. */
function invalidateCode(client: ReturnType<typeof useQueryClient>, pid: string) {
  void client.invalidateQueries({ queryKey: qk.imports(pid) });
  void client.invalidateQueries({ queryKey: qk.analysis(pid) });
  void client.invalidateQueries({ queryKey: qk.overview(pid) });
  void client.invalidateQueries({ queryKey: qk.project(pid) });
  void client.invalidateQueries({ queryKey: qk.projects });
}

export function useImportGithub(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { repo?: string | null; ref?: string | null }) =>
      unwrap(api.POST("/api/v1/projects/{project_id}/imports/github", { params: { path: { project_id: pid }, query: { wait: 0 } }, body })),
    onSuccess: () => invalidateCode(client, pid),
  });
}

export function useImportZip(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file, file.name);
      return rawJson<Import>("POST", `/api/v1/projects/${pid}/imports/zip?wait=0`, form);
    },
    onSuccess: () => invalidateCode(client, pid),
  });
}

/** Called once an import finishes, so every view picks up the new current code. */
export function useRefreshAfterImport(pid: string) {
  const client = useQueryClient();
  return () => invalidateCode(client, pid);
}

export function useAnalysis(pid: string) {
  return useQuery({
    queryKey: qk.analysis(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/analysis", p(pid))),
    staleTime: STALE.list,
  });
}
