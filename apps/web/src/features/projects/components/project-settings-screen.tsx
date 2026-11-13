"use client";

import { Building2Icon, CpuIcon, GithubIcon, KeyRoundIcon, SlidersHorizontalIcon, Trash2Icon, UsersIcon, WebhookIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { GithubTab } from "@/features/integrations/components/github-tab";
import { WebhooksTab } from "@/features/integrations/components/webhooks-tab";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Hint } from "@/components/hint";
import { RoleNote } from "@/components/role-note";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { errorMessage } from "@/lib/api/errors";
import type { Project } from "@/lib/api/types";
import { useUiPrefs } from "@/lib/store";
import { useTabParam } from "@/lib/use-tab-param";

import { useCurrentProject, useDeleteProject, useUpdateProject } from "../api";

import { ApiKeysTab } from "./api-keys-tab";
import { MembersTab } from "./members-tab";
import { OrganizationTab } from "./organization-tab";
import { ProvidersTab } from "./providers-tab";

const TABS = ["project", "members", "providers", "api-keys", "github", "webhooks", "organization"] as const;

export function ProjectSettingsScreen() {
  const { pid, project, canAdmin, query } = useCurrentProject();
  const [rawTab, setTab] = useTabParam("project", TABS);
  // API keys are an admin's tool; everyone else lands on the project tab.
  const tab = rawTab === "api-keys" && project && !canAdmin ? "project" : rawTab;
  // On a phone the tab strip scrolls sideways; keep the open tab in view.
  const strip = React.useRef<HTMLDivElement>(null);
  const ready = !query.isPending && !query.isError;
  React.useEffect(() => {
    const active = strip.current?.querySelector<HTMLElement>("[aria-selected=true]");
    if (active && strip.current) strip.current.scrollLeft = Math.max(0, active.offsetLeft - 16);
  }, [tab, ready]);

  return (
    <>
      <PageHeader title="Settings" description="This project and its run limits, who works in it, the models that write its tests, the keys your CI uses, GitHub, webhooks and the organization around it." />
      {query.isPending ? (
        <Skeleton className="h-96 w-full max-w-3xl rounded-[14px]" />
      ) : query.isError ? (
        <div className="surface">
          <ErrorState error={query.error} title="Project settings could not be loaded" onRetry={() => void query.refetch()} />
        </div>
      ) : (
        <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
          <div ref={strip} className="no-scrollbar relative -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
            <TabsList className="flex-nowrap">
              <TabsTrigger value="project">
                <SlidersHorizontalIcon />
                Project
              </TabsTrigger>
              <TabsTrigger value="members">
                <UsersIcon />
                Members
              </TabsTrigger>
              <TabsTrigger value="providers">
                <CpuIcon />
                Model providers
              </TabsTrigger>
              {canAdmin && (
                <TabsTrigger value="api-keys">
                  <KeyRoundIcon />
                  API keys
                </TabsTrigger>
              )}
              <TabsTrigger value="github">
                <GithubIcon />
                GitHub
              </TabsTrigger>
              <TabsTrigger value="webhooks">
                <WebhookIcon />
                Webhooks
              </TabsTrigger>
              <TabsTrigger value="organization">
                <Building2Icon />
                Organization
              </TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="project">
            <GeneralTab key={query.data.id} project={query.data} canAdmin={canAdmin} />
          </TabsContent>
          <TabsContent value="members">
            <MembersTab pid={pid} canAdmin={canAdmin} />
          </TabsContent>
          {canAdmin && (
            <TabsContent value="api-keys">
              <ApiKeysTab pid={pid} />
            </TabsContent>
          )}
          <TabsContent value="providers">
            <ProvidersTab pid={pid} canAdmin={canAdmin} />
          </TabsContent>
          <TabsContent value="github">
            <GithubTab key={query.data.id} project={query.data} canAdmin={canAdmin} />
          </TabsContent>
          <TabsContent value="webhooks">
            <WebhooksTab pid={pid} canAdmin={canAdmin} />
          </TabsContent>
          <TabsContent value="organization">
            <OrganizationTab orgId={query.data.org_id} />
          </TabsContent>
        </Tabs>
      )}
    </>
  );
}

function GeneralTab({ project: p, canAdmin }: { project: Project; canAdmin: boolean }) {
  const update = useUpdateProject(p.id);
  const [name, setName] = React.useState(p.name);
  const [description, setDescription] = React.useState(p.description);
  const [error, setError] = React.useState<string | null>(null);
  const ro = !canAdmin;

  function save(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("The project needs a name.");
    setError(null);
    update.mutate(
      { name: name.trim(), description: description.trim() },
      { onSuccess: () => toast.success("Project settings saved."), onError: (err) => setError(errorMessage(err)) },
    );
  }

  return (
    <div className="max-w-3xl space-y-4">
      {ro && <RoleNote>Only project admins change these settings.</RoleNote>}
      <form onSubmit={save} noValidate>
        <Surface>
          <SurfaceHeader title="About" />
          <div className="grid gap-4 px-5 pb-5">
            <Field label="Name" htmlFor="ps-name">
              <Input id="ps-name" maxLength={120} disabled={ro} value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Description" htmlFor="ps-desc">
              <Textarea id="ps-desc" maxLength={2000} disabled={ro} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
          </div>
          {canAdmin && (
            <div className="flex flex-col gap-2 rounded-b-[14px] bg-muted/50 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
              <div>{error && <FieldError>{error}</FieldError>}</div>
              <Button type="submit" disabled={update.isPending}>
                {update.isPending ? "Saving..." : "Save settings"}
              </Button>
            </div>
          )}
        </Surface>
      </form>
      <LimitsCard project={p} canAdmin={canAdmin} />
      {canAdmin && <DangerZone project={p} />}
    </div>
  );
}

function DangerZone({ project }: { project: Project }) {
  const del = useDeleteProject(project.id);
  const router = useRouter();
  const setLast = useUiPrefs((s) => s.setLastProject);
  const [open, setOpen] = React.useState(false);
  const [typed, setTyped] = React.useState("");
  React.useEffect(() => {
    if (open) setTyped("");
  }, [open]);

  return (
    <Surface>
      <SurfaceHeader title="Danger zone" />
      <div className="flex flex-col gap-3 px-5 pb-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[13px] leading-relaxed text-muted-foreground">
          Delete this project with its imports, generated tests, runs, coverage, reports, model providers and API keys. Your
          repository is never touched: TestForge only ever read it.
        </p>
        <Button variant="destructive-soft" onClick={() => setOpen(true)} className="shrink-0">
          <Trash2Icon />
          Delete project
        </Button>
      </div>
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title={`Delete ${project.name}?`}
        description="This cannot be undone. CI jobs that use its API keys start failing at once."
        confirmLabel="Delete forever"
        pending={del.isPending}
        confirmDisabled={typed !== project.name}
        onConfirm={() => {
          if (typed !== project.name) return;
          del.mutate(undefined, {
            onSuccess: () => {
              setLast(null);
              toast.success(`${project.name} deleted.`);
              router.replace("/projects");
            },
            onError: (err) => toast.error(errorMessage(err)),
          });
        }}
      >
        <Field label={<span>Type <span className="font-mono">{project.name}</span> to confirm</span>} htmlFor="del-confirm">
          <Input id="del-confirm" autoComplete="off" value={typed} onChange={(e) => setTyped(e.target.value)} aria-invalid={typed.length > 0 && typed !== project.name ? true : undefined} />
        </Field>
        {typed.length > 0 && typed !== project.name && <p className="mt-1.5 text-[12px] text-muted-foreground">The name does not match yet.</p>}
      </ConfirmDialog>
    </Surface>
  );
}

const LIMITS = [
  { key: "run_cpu_s", label: "CPU time", unit: "seconds", min: 1, max: 3600, fallback: 60 },
  { key: "run_wall_s", label: "Wall clock", unit: "seconds", min: 1, max: 3600, fallback: 120 },
  { key: "run_memory_mb", label: "Memory", unit: "MB", min: 64, max: 16384, fallback: 1024 },
  { key: "run_output_bytes", label: "Output", unit: "bytes", min: 1024, max: 100_000_000, fallback: 4_000_000 },
] as const;

type LimitKey = (typeof LIMITS)[number]["key"];

/** A limit field's value, or null to use the instance default; undefined when it is not a valid number. */
export function parseLimit(raw: string, min: number, max: number): number | null | undefined {
  const t = raw.trim();
  if (!t) return null;
  if (!/^\d+$/.test(t)) return undefined;
  const n = Number(t);
  return n >= min && n <= max ? n : undefined;
}

function LimitsCard({ project: p, canAdmin }: { project: Project; canAdmin: boolean }) {
  const update = useUpdateProject(p.id);
  const [values, setValues] = React.useState<Record<LimitKey, string>>(() => ({
    run_cpu_s: p.run_cpu_s?.toString() ?? "",
    run_wall_s: p.run_wall_s?.toString() ?? "",
    run_memory_mb: p.run_memory_mb?.toString() ?? "",
    run_output_bytes: p.run_output_bytes?.toString() ?? "",
  }));
  const [error, setError] = React.useState<string | null>(null);

  function save(e: React.FormEvent) {
    e.preventDefault();
    const body: Partial<Record<LimitKey, number | null>> = {};
    for (const l of LIMITS) {
      const v = parseLimit(values[l.key], l.min, l.max);
      if (v === undefined) return setError(`${l.label} must be a whole number from ${l.min} to ${l.max} ${l.unit}, or empty for the default.`);
      body[l.key] = v;
    }
    setError(null);
    update.mutate(body, { onSuccess: () => toast.success("Run limits saved. They apply to the next run."), onError: (err) => setError(errorMessage(err)) });
  }

  return (
    <form onSubmit={save} noValidate>
      <Surface>
        <SurfaceHeader
          title={
            <span className="inline-flex items-center gap-1.5">
              Run limits <Hint term="limit" />
            </span>
          }
          description="The most one run may use. A run that crosses a limit is stopped and reported with the limit it crossed. Empty uses the instance default."
        />
        <div className="grid gap-4 px-5 pb-5 sm:grid-cols-2">
          {LIMITS.map((l) => (
            <Field key={l.key} label={`${l.label} (${l.unit})`} htmlFor={`lim-${l.key}`}>
              <Input
                id={`lim-${l.key}`}
                inputMode="numeric"
                disabled={!canAdmin}
                placeholder={`Default, ${l.fallback.toLocaleString("en-US")}`}
                value={values[l.key]}
                onChange={(e) => setValues((v) => ({ ...v, [l.key]: e.target.value }))}
              />
            </Field>
          ))}
        </div>
        {canAdmin && (
          <div className="flex flex-col gap-2 rounded-b-[14px] bg-muted/50 px-5 py-3.5 sm:flex-row sm:items-center sm:justify-between">
            <div>{error && <FieldError>{error}</FieldError>}</div>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save limits"}
            </Button>
          </div>
        )}
      </Surface>
    </form>
  );
}
