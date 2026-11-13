"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { FileContent, SourceFile, Unit, UnitDetail } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

const pi = (pid: string, iid: string) => ({ project_id: pid, import_id: iid });

export function useFiles(pid: string, iid: string | null | undefined) {
  return useQuery<SourceFile[]>({
    queryKey: qk.files(pid, iid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/imports/{import_id}/files", { params: { path: pi(pid, iid as string) } })),
    enabled: !!iid,
    staleTime: STALE.static,
  });
}

/** One file's text with its units and, after a run, its covered and missing lines. */
export function useFile(pid: string, iid: string | null | undefined, path: string | null) {
  return useQuery<FileContent>({
    queryKey: qk.file(pid, iid ?? "", path ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{project_id}/imports/{import_id}/file", { params: { path: pi(pid, iid as string), query: { path: path as string } } })),
    enabled: !!iid && !!path,
    staleTime: STALE.list,
  });
}

export interface UnitFilters {
  kind?: string;
  untested?: boolean;
  file?: string;
}

export function useUnits(pid: string, iid: string | null | undefined, filters: UnitFilters = {}) {
  return useQuery<Unit[]>({
    queryKey: qk.units(pid, iid ?? "", filters),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/imports/{import_id}/units", {
          params: {
            path: pi(pid, iid as string),
            query: { kind: filters.kind || null, untested: filters.untested ? true : undefined, file: filters.file || null },
          },
        }),
      ),
    enabled: !!iid,
    staleTime: STALE.list,
  });
}

export function useUnit(pid: string, iid: string | null | undefined, uid: string | null | undefined) {
  return useQuery<UnitDetail>({
    queryKey: qk.unit(pid, iid ?? "", uid ?? ""),
    queryFn: () =>
      unwrap(api.GET("/api/v1/projects/{project_id}/imports/{import_id}/units/{unit_id}", { params: { path: { ...pi(pid, iid as string), unit_id: uid as string } } })),
    enabled: !!iid && !!uid,
    staleTime: STALE.static,
  });
}
