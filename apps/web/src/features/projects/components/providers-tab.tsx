"use client";

import { CheckCircle2Icon, CpuIcon, PlugZapIcon, PlusIcon, StarIcon, Trash2Icon, XCircleIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { RoleNote } from "@/components/role-note";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useCreateProvider, useDeleteProvider, useProviders, useTestProvider, useUpdateProvider } from "@/features/providers/api";
import { errorMessage } from "@/lib/api/errors";
import type { Provider, ProviderKind } from "@/lib/api/types";
import { formatRelative } from "@/lib/format";

const KINDS: { value: ProviderKind; label: string; model: string; needsUrl: boolean; needsKey: boolean }[] = [
  { value: "openai", label: "OpenAI", model: "gpt-4.1-mini", needsUrl: false, needsKey: true },
  { value: "anthropic", label: "Anthropic", model: "claude-sonnet-4-5", needsUrl: false, needsKey: true },
  { value: "gemini", label: "Google Gemini", model: "gemini-2.5-flash", needsUrl: false, needsKey: true },
  { value: "ollama", label: "Ollama (local models)", model: "qwen2.5-coder:7b", needsUrl: true, needsKey: false },
  { value: "openai_compatible", label: "OpenAI-compatible endpoint", model: "", needsUrl: true, needsKey: false },
  { value: "mock", label: "Built-in mock (no key, for trying TestForge)", model: "testforge-mock", needsUrl: false, needsKey: false },
];

export function kindLabel(kind: string): string {
  return KINDS.find((k) => k.value === kind)?.label.split(" (")[0] ?? kind;
}

/** The models that write this project's tests. Admins add them; everyone sees which exist. */
export function ProvidersTab({ pid, canAdmin }: { pid: string; canAdmin: boolean }) {
  const q = useProviders(pid);
  const [adding, setAdding] = React.useState(false);
  const list = q.data ?? [];
  return (
    <div className="max-w-4xl space-y-4">
      {!canAdmin && <RoleNote>Project admins add model providers and choose the default one.</RoleNote>}
      <Surface className="overflow-hidden">
        <SurfaceHeader
          title={
            <span className="inline-flex items-center gap-1.5">
              Model providers <Hint term="provider" />
            </span>
          }
          description="Generation uses the default provider unless you pick another. Keys are sealed and never shown again."
          action={
            canAdmin && (
              <Button size="sm" onClick={() => setAdding(true)}>
                <PlusIcon />
                Add provider
              </Button>
            )
          }
        />
        {q.isPending ? (
          <TableSkeleton rows={3} cols={4} />
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} compact />
        ) : !list.length ? (
          <EmptyState
            compact
            icon={CpuIcon}
            title="No model provider yet"
            description="Bring your own key for OpenAI, Anthropic, Gemini or any OpenAI-compatible endpoint, run a local model with Ollama, or start with the built-in mock."
            action={
              canAdmin ? (
                <Button size="sm" onClick={() => setAdding(true)}>
                  <PlusIcon />
                  Add provider
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="divide-y divide-hairline px-5 pb-2">
            {list.map((p) => (
              <ProviderRow key={p.id} pid={pid} p={p} canAdmin={canAdmin} />
            ))}
          </ul>
        )}
      </Surface>
      <AddProviderDialog pid={pid} open={adding} onOpenChange={setAdding} />
    </div>
  );
}

function ProviderRow({ pid, p, canAdmin }: { pid: string; p: Provider; canAdmin: boolean }) {
  const test = useTestProvider(pid);
  const update = useUpdateProvider(pid);
  const del = useDeleteProvider(pid);
  const [deleting, setDeleting] = React.useState(false);
  return (
    <li className="flex flex-col gap-3 py-3.5 sm:flex-row sm:items-center sm:justify-between" data-qa="provider">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{p.name}</span>
          <Chip tone="neutral">{kindLabel(p.kind)}</Chip>
          {p.is_default && (
            <Chip tone="primary">
              <StarIcon aria-hidden />
              Default
            </Chip>
          )}
          {!p.enabled && <Chip tone="warning">Off</Chip>}
        </div>
        <div className="mt-0.5 truncate text-[12px] text-subtle">
          <span className="font-mono">{p.model}</span>
          {p.base_url ? ` at ${p.base_url}` : ""}
          {p.has_api_key ? ", key stored" : ""}
        </div>
        {p.last_test_at && (
          <div className={`mt-0.5 inline-flex items-center gap-1 text-[12px] ${p.last_test_ok ? "text-savings" : "text-danger"}`}>
            {p.last_test_ok ? <CheckCircle2Icon className="size-3.5" /> : <XCircleIcon className="size-3.5" />}
            {p.last_test_message} ({formatRelative(p.last_test_at)})
          </div>
        )}
      </div>
      {canAdmin && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 text-[12.5px] text-muted-foreground">
            <Switch
              checked={p.enabled}
              onCheckedChange={(enabled) => update.mutate({ id: p.id, body: { enabled } }, { onError: (err) => toast.error(errorMessage(err)) })}
              aria-label={`Turn ${p.name} on or off`}
            />
            On
          </label>
          {!p.is_default && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => update.mutate({ id: p.id, body: { is_default: true } }, { onError: (err) => toast.error(errorMessage(err)) })}
            >
              Make default
            </Button>
          )}
          <Button
            variant="outline"
            size="xs"
            disabled={test.isPending}
            onClick={() => test.mutate(p.id, { onSuccess: (r) => (r.ok ? toast.success(r.message) : toast.error(r.message)), onError: (err) => toast.error(errorMessage(err)) })}
          >
            <PlugZapIcon />
            {test.isPending ? "Testing..." : "Test"}
          </Button>
          <Button variant="subtle" size="icon-xs" aria-label={`Remove ${p.name}`} onClick={() => setDeleting(true)}>
            <Trash2Icon />
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={deleting}
        onOpenChange={setDeleting}
        title={`Remove ${p.name}?`}
        description="Its sealed key is deleted. Generations already made keep their tests; new ones use the default provider."
        confirmLabel="Remove provider"
        pending={del.isPending}
        onConfirm={() => del.mutate(p.id, { onSuccess: () => setDeleting(false), onError: (err) => toast.error(errorMessage(err)) })}
      />
    </li>
  );
}

function AddProviderDialog({ pid, open, onOpenChange }: { pid: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const create = useCreateProvider(pid);
  const [kind, setKind] = React.useState<ProviderKind>("openai");
  const [name, setName] = React.useState("openai");
  const [model, setModel] = React.useState("gpt-4.1-mini");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [apiKey, setApiKey] = React.useState("");
  const [isDefault, setIsDefault] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const spec = KINDS.find((k) => k.value === kind) ?? KINDS[0];
  React.useEffect(() => {
    if (!open) return;
    setKind("openai");
    setName("openai");
    setModel("gpt-4.1-mini");
    setBaseUrl("");
    setApiKey("");
    setIsDefault(false);
    setError(null);
  }, [open]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!/^[a-z0-9][a-z0-9_-]{0,63}$/.test(name)) return setError("The name is short, lower case: letters, digits, - and _.");
    if (spec?.needsUrl && kind === "openai_compatible" && !baseUrl.trim()) return setError("An OpenAI-compatible endpoint needs its base URL, ending in /v1.");
    if (kind === "openai_compatible" && !model.trim()) return setError("Name the model to use.");
    setError(null);
    create.mutate(
      { name, kind, model: model.trim(), base_url: baseUrl.trim() || null, api_key: apiKey || null, is_default: isDefault },
      {
        onSuccess: () => {
          toast.success(`${name} added.`);
          onOpenChange(false);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent>
        <form onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>Add a model provider</DialogTitle>
            <DialogDescription>The model writes tests from the analyzed source. Nothing it writes is shown without a real assertion, or runs outside the sandbox.</DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-4">
            <Field label="Provider" htmlFor="pv-kind">
              <SimpleSelect
                id="pv-kind"
                value={kind}
                onValueChange={(v) => {
                  const k = KINDS.find((x) => x.value === v);
                  setKind(v as ProviderKind);
                  setName(v.replace("_", "-"));
                  setModel(k?.model ?? "");
                }}
                options={KINDS.map((k) => ({ value: k.value, label: k.label }))}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name" htmlFor="pv-name">
                <Input id="pv-name" value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              {kind !== "mock" && (
                <Field label="Model" htmlFor="pv-model">
                  <Input id="pv-model" value={model} onChange={(e) => setModel(e.target.value)} className="font-mono" />
                </Field>
              )}
            </div>
            {kind !== "mock" && (
              <>
                <Field label={spec?.needsUrl ? "Base URL" : "Base URL (optional)"} htmlFor="pv-url" hint={kind === "openai_compatible" ? "Any endpoint that speaks the OpenAI API, ending in /v1." : undefined}>
                  <Input id="pv-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder={kind === "ollama" ? "http://localhost:11434" : "https://"} />
                </Field>
                <Field label={spec?.needsKey ? "API key" : "API key (optional)"} htmlFor="pv-key">
                  <Input id="pv-key" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
                </Field>
              </>
            )}
            <label className="flex items-center gap-3 text-[13px]">
              <Switch checked={isDefault} onCheckedChange={setIsDefault} aria-label="Make it the default" />
              Make it the project&apos;s default
            </label>
            {error && <FieldError role="alert">{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Adding..." : "Add provider"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
