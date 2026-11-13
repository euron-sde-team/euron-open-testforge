"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";
import type { Delivery, Webhook, WebhookCreate } from "@/lib/api/types";
import { qk, STALE } from "@/lib/query-keys";

const p = (pid: string) => ({ params: { path: { project_id: pid } } });

export function useWebhooks(pid: string) {
  return useQuery<Webhook[]>({
    queryKey: qk.webhooks(pid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/webhooks", p(pid))),
    staleTime: STALE.list,
  });
}

export function useCreateWebhook(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: WebhookCreate) => unwrap(api.POST("/api/v1/projects/{project_id}/webhooks", { ...p(pid), body })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.webhooks(pid) }),
  });
}

export function useDeleteWebhook(pid: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/api/v1/projects/{project_id}/webhooks/{webhook_id}", { params: { path: { project_id: pid, webhook_id: id } } })),
    onSuccess: () => client.invalidateQueries({ queryKey: qk.webhooks(pid) }),
  });
}

export function useDeliveries(pid: string, wid: string, enabled = true) {
  return useQuery<Delivery[]>({
    queryKey: qk.deliveries(pid, wid),
    queryFn: () => unwrap(api.GET("/api/v1/projects/{project_id}/webhooks/{webhook_id}/deliveries", { params: { path: { project_id: pid, webhook_id: wid } } })),
    staleTime: STALE.list,
    enabled,
  });
}

/** A new GitHub webhook secret; the previous one stops working at once. */
export function useRotateGithubSecret(pid: string) {
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/v1/projects/{project_id}/github/webhook-secret", p(pid))),
  });
}
