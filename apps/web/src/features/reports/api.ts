"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, download, unwrap } from "@/lib/api/client";
import type { Report, ReportCreate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useReports(pid: string) {
  return useQuery<Report[]>({
    queryKey: qk.reports(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/reports", { params: { path: { project_id: pid } } })),
    staleTime: STALE.list,
  });
}

export function useCreateReport(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ReportCreate) => unwrap(api.POST("/api/v1/projects/{project_id}/reports", { params: { path: { project_id: pid } }, body })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.reports(pid) }),
  });
}

export function useDownloadReport(pid: string) {
  return useMutation({
    mutationFn: (r: Report) => download(`/api/v1/projects/${pid}/reports/${r.id}/download`, `testforge-report.${r.format}`),
  });
}
