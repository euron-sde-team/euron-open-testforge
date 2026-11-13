"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Org, OrgMember, OrgMemberAdd, OrgRole } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

const o = (oid: string) => ({ params: { path: { org_id: oid } } });

/** Organizations the signed-in person belongs to, with their role in each. */
export function useOrgs() {
  return useQuery<Org[]>({ queryKey: qk.orgs, queryFn: () => unwrap(api.GET("/api/v1/orgs")), staleTime: STALE.list });
}

export function useOrg(oid: string | undefined) {
  return useQuery({
    queryKey: qk.org(oid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}", o(oid as string))),
    staleTime: STALE.config,
    enabled: !!oid,
  });
}

export function useCreateOrg() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) => unwrap(api.POST("/api/v1/orgs", { body })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.orgs }),
  });
}

export function useUpdateOrg(oid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) => unwrap(api.PATCH("/api/v1/orgs/{org_id}", { ...o(oid), body })),
    onSuccess: (data) => {
      client.setQueryData(qk.org(oid), data);
      void client.invalidateQueries({ queryKey: qk.orgs });
    },
  });
}

export function useOrgMembers(oid: string | undefined) {
  return useQuery<OrgMember[]>({
    queryKey: qk.orgMembers(oid ?? ""),
    queryFn: () => unwrap(api.GET("/api/v1/orgs/{org_id}/members", o(oid as string))),
    staleTime: STALE.list,
    enabled: !!oid,
  });
}

export function useAddOrgMember(oid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: OrgMemberAdd) => unwrap(api.POST("/api/v1/orgs/{org_id}/members", { ...o(oid), body })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.orgMembers(oid) }),
  });
}

export function useUpdateOrgMember(oid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: OrgRole }) =>
      unwrap(api.PATCH("/api/v1/orgs/{org_id}/members/{user_id}", { params: { path: { org_id: oid, user_id: userId } }, body: { role } })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.orgMembers(oid) }),
  });
}

export function useRemoveOrgMember(oid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      unwrap(api.DELETE("/api/v1/orgs/{org_id}/members/{user_id}", { params: { path: { org_id: oid, user_id: userId } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.orgMembers(oid) }),
  });
}

export function useOrgAudit(oid: string | undefined, action?: string) {
  return useInfiniteQuery({
    queryKey: qk.orgAudit(oid ?? "", action),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/orgs/{org_id}/audit-logs", {
          params: { path: { org_id: oid as string }, query: { cursor: pageParam, limit: 50, action: action || null } },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? null,
    staleTime: STALE.config,
    enabled: !!oid,
  });
}
