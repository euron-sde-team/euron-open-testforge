"use client";

import { CheckIcon, ChevronDownIcon, ChevronRightIcon, PlusIcon, Trash2Icon, TriangleAlertIcon, WebhookIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { CopyButton } from "@/components/copy-button";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { RoleNote } from "@/components/role-note";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError, Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import type { Webhook, WebhookCreated, WebhookEvent } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";

import { useCreateWebhook, useDeleteWebhook, useDeliveries, useWebhooks } from "../api";

const EVENTS: { value: WebhookEvent; label: string }[] = [
  { value: "run.finished", label: "A run finished" },
  { value: "generation.finished", label: "A generation finished" },
  { value: "import.ready", label: "An import was analyzed" },
];

/** Outbound webhooks: TestForge tells your systems when a run, generation or import finishes. */
export function WebhooksTab({ pid, canAdmin }: { pid: string; canAdmin: boolean }) {
  const q = useWebhooks(pid);
  const [adding, setAdding] = React.useState(false);
  const [created, setCreated] = React.useState<WebhookCreated | null>(null);
  const list = q.data ?? [];
  return (
    <div className="max-w-4xl space-y-4">
      {!canAdmin && <RoleNote>Project admins add and remove webhooks. Everyone sees where events go and how deliveries went.</RoleNote>}
      <Surface className="overflow-hidden">
        <SurfaceHeader
          title="Outbound webhooks"
          description="Each delivery is signed with the webhook's secret and retried with backoff if your endpoint fails."
          action={
            canAdmin && list.length > 0 ? (
              <Button size="sm" onClick={() => setAdding(true)}>
                <PlusIcon />
                Add webhook
              </Button>
            ) : undefined
          }
        />
        {q.isPending ? (
          <TableSkeleton rows={2} cols={3} />
        ) : q.isError ? (
          <ErrorState compact error={q.error} onRetry={() => void q.refetch()} />
        ) : !list.length ? (
          <EmptyState
            compact
            icon={WebhookIcon}
            title="No webhooks"
            description="Send a signed request to your chat bot, CI or dashboard when a run finishes, tests are generated or an import is ready."
            action={
              canAdmin ? (
                <Button size="sm" onClick={() => setAdding(true)}>
                  <PlusIcon />
                  Add webhook
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="divide-y divide-hairline px-5 pb-2">
            {list.map((w) => (
              <WebhookRow key={w.id} pid={pid} w={w} canAdmin={canAdmin} />
            ))}
          </ul>
        )}
      </Surface>
      <AddWebhookDialog
        pid={pid}
        open={adding}
        onOpenChange={setAdding}
        onCreated={(w) => {
          setAdding(false);
          setCreated(w);
        }}
      />
      <Dialog open={!!created} onOpenChange={(o) => !o && setCreated(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Copy the signing secret</DialogTitle>
            <DialogDescription>{created?.name}: verify each delivery&apos;s signature with this secret. It is shown only now.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <div className="flex items-center gap-2 rounded-xl bg-muted p-2 pl-3">
              <code className="min-w-0 flex-1 truncate font-mono text-[12.5px]">{created?.secret}</code>
              <CopyButton value={created?.secret ?? ""} variant="default" />
            </div>
            <p className="flex items-start gap-2 text-[12.5px] text-warning">
              <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
              Store it where your endpoint runs. To change it, remove the webhook and add it again.
            </p>
          </DialogBody>
          <DialogFooter>
            <Button onClick={() => setCreated(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function WebhookRow({ pid, w, canAdmin }: { pid: string; w: Webhook; canAdmin: boolean }) {
  const [open, setOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);
  const del = useDeleteWebhook(pid);
  const deliveries = useDeliveries(pid, w.id, open);
  return (
    <li className="py-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="flex min-w-0 items-start gap-2 text-left focus-visible:outline-2 focus-visible:outline-ring">
          {open ? <ChevronDownIcon className="mt-0.5 size-4 shrink-0 text-subtle" /> : <ChevronRightIcon className="mt-0.5 size-4 shrink-0 text-subtle" />}
          <span className="min-w-0">
            <span className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{w.name}</span>
              {!w.enabled && <Chip tone="warning">Off</Chip>}
            </span>
            <span className="block truncate font-mono text-[12px] text-subtle">{w.url}</span>
            <span className="mt-1 flex flex-wrap gap-1">
              {w.events.map((e) => (
                <Chip key={e} tone="neutral" className="font-mono">
                  {e}
                </Chip>
              ))}
            </span>
          </span>
        </button>
        {canAdmin && (
          <Button variant="subtle" size="icon-xs" aria-label={`Remove ${w.name}`} onClick={() => setDeleting(true)}>
            <Trash2Icon />
          </Button>
        )}
      </div>
      {open && (
        <div className="mt-2 rounded-xl bg-muted/60 px-4 py-3 sm:ml-6">
          <Label className="mb-1.5 text-[12px] text-muted-foreground">Recent deliveries</Label>
          {deliveries.isPending ? (
            <p className="text-[12.5px] text-muted-foreground">Loading...</p>
          ) : deliveries.isError ? (
            <ErrorState compact error={deliveries.error} />
          ) : !deliveries.data?.length ? (
            <p className="text-[12.5px] text-muted-foreground">Nothing delivered yet. The first event after it was added appears here.</p>
          ) : (
            <ul className="space-y-1 text-[12.5px]">
              {deliveries.data.map((d) => (
                <li key={d.id} className="flex flex-wrap items-center gap-2">
                  <Chip tone={d.status === "delivered" ? "success" : d.status === "failed" ? "danger" : "neutral"}>{d.status}</Chip>
                  <span className="font-mono">{d.event}</span>
                  <span className="text-subtle">
                    {d.last_status_code ? `HTTP ${d.last_status_code}, ` : ""}
                    {d.attempts} {d.attempts === 1 ? "attempt" : "attempts"}, {formatRelative(d.created_at)}
                  </span>
                  {d.last_error && <span className="w-full truncate text-danger">{d.last_error}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Remove ${w.name}?`}
        description="No more events are sent to it. Its delivery history is removed with it."
        confirmLabel="Remove webhook"
        pending={del.isPending}
        onConfirm={() => del.mutate(w.id, { onSuccess: () => setDeleting(false), onError: (err) => toast.error(errorMessage(err)) })}
      />
    </li>
  );
}

function AddWebhookDialog({ pid, open, onOpenChange, onCreated }: { pid: string; open: boolean; onOpenChange: (o: boolean) => void; onCreated: (w: WebhookCreated) => void }) {
  const create = useCreateWebhook(pid);
  const [name, setName] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [events, setEvents] = React.useState<WebhookEvent[]>(["run.finished"]);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!open) return;
    setName("");
    setUrl("");
    setEvents(["run.finished"]);
    setError(null);
  }, [open]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Name the webhook after where it goes, like 'Team chat'.");
    if (!/^https?:\/\//.test(url.trim())) return setError("The URL starts with https:// (or http:// for a local service).");
    if (!events.length) return setError("Pick at least one event.");
    setError(null);
    create.mutate({ name: name.trim(), url: url.trim(), events }, { onSuccess: onCreated, onError: (err) => setError(errorMessage(err)) });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a webhook</DialogTitle>
          <DialogDescription>The signing secret is shown once, right after this.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="wh-name">
              <Input id="wh-name" placeholder="Team chat" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="URL" htmlFor="wh-url">
              <Input id="wh-url" placeholder="https://hooks.example.com/testforge" value={url} onChange={(e) => setUrl(e.target.value)} />
            </Field>
            <div className="space-y-1.5">
              <Label>Events</Label>
              <div className="grid gap-2">
                {EVENTS.map((ev) => {
                  const on = events.includes(ev.value);
                  return (
                    <button
                      key={ev.value}
                      type="button"
                      role="checkbox"
                      aria-checked={on}
                      onClick={() => setEvents((cur) => (on ? cur.filter((x) => x !== ev.value) : [...cur, ev.value]))}
                      className={cn("flex items-center gap-2.5 rounded-xl bg-muted px-3 py-2 text-left text-[13px] hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring", on && "bg-primary-soft hover:bg-primary-soft")}
                    >
                      <span className={cn("flex size-4 shrink-0 items-center justify-center rounded ring-1 ring-input", on && "bg-primary text-primary-foreground ring-primary")}>
                        {on && <CheckIcon className="size-3" strokeWidth={3} />}
                      </span>
                      {ev.label} <span className="font-mono text-[11.5px] text-subtle">{ev.value}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Adding..." : "Add webhook"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
