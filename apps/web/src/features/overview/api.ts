"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Overview } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

export function useOverview(pid: string) {
  return useQuery<Overview>({
    queryKey: qk.overview(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/overview", { params: { path: { project_id: pid } } })),
    staleTime: STALE.list,
    refetchInterval: 30_000,
  });
}
