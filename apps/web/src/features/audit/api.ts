"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import { qk, STALE } from "@/lib/query-keys";

export function useAuditLog(action?: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: qk.audit(action),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/api/v1/audit", { params: { query: { cursor: pageParam, limit: 50, action: action || null } } })),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: STALE.config,
    enabled,
  });
}

export interface ProjectAuditFilters {
  action?: string;
  targetId?: string;
  actorId?: string;
}

/** The project's audit log, filtered to one action, one record or one person if asked. */
export function useProjectAudit(pid: string, filters: ProjectAuditFilters, enabled = true) {
  return useInfiniteQuery({
    queryKey: qk.projectAudit(pid, filters),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/projects/{project_id}/audit-logs", {
          params: {
            path: { project_id: pid },
            query: {
              cursor: pageParam,
              limit: 50,
              action: filters.action || null,
              target_id: filters.targetId || null,
              actor_id: filters.actorId || null,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: STALE.list,
    enabled,
  });
}
