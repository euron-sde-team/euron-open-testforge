"use client";

import { ArrowRightIcon, Building2Icon, FileCode2Icon, FlaskConicalIcon, FolderPlusIcon, PlusIcon, ShieldCheckIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { BrandMark } from "@/components/brand";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { CoverageBar, RunStatusChip } from "@/components/status-chips";
import { useCreateOrg, useOrgs } from "@/features/orgs/api";
import { errorMessage } from "@/lib/api/errors";
import type { Org, Project } from "@/lib/api/types";
import { formatNumber, formatPercent } from "@/lib/format";
import { canOrg, ORG_ROLE_LABEL } from "@/lib/roles";
import { useUiPrefs } from "@/lib/store";

import { useCreateProject, useProjects } from "../api";

export function ProjectsScreen() {
  const q = useProjects();
  const orgs = useOrgs();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const lastOrg = useUiPrefs((s) => s.lastOrgId);
  const setLastOrg = useUiPrefs((s) => s.setLastOrg);
  const [open, setOpen] = React.useState(false);
  const [orgOpen, setOrgOpen] = React.useState(false);

  React.useEffect(() => {
    if (params.get("new") === "1") setOpen(true);
  }, [params]);

  function setDialog(next: boolean) {
    setOpen(next);
    if (!next && params.get("new")) router.replace(pathname, { scroll: false });
  }

  const orgList = orgs.data ?? [];
  const orgId = orgList.find((o) => o.id === params.get("org"))?.id ?? orgList.find((o) => o.id === lastOrg)?.id ?? orgList[0]?.id ?? "";
  const org = orgList.find((o) => o.id === orgId);
  const projects = (q.data ?? []).filter((p) => !orgId || p.org_id === orgId);
  const canCreate = canOrg(org?.role, "admin");

  function chooseOrg(id: string) {
    setLastOrg(id);
    router.replace(`${pathname}?org=${id}`, { scroll: false });
  }

  return (
    <>
      <PageHeader
        title="Projects"
        description="A project is one codebase: its imports, generated tests, sandboxed runs, coverage and pull requests, with its own members, model providers and API keys."
        actions={
          <>
            {orgList.length > 0 && (
              <SimpleSelect
                aria-label="Organization"
                className="w-56"
                value={orgId}
                onValueChange={chooseOrg}
                options={orgList.map((o) => ({ value: o.id, label: o.name }))}
              />
            )}
            <Button variant="outline" onClick={() => setOrgOpen(true)}>
              <Building2Icon />
              New organization
            </Button>
            {projects.length > 0 && canCreate && (
              <Button onClick={() => setDialog(true)}>
                <FolderPlusIcon />
                New project
              </Button>
            )}
          </>
        }
      />
      {org && <OrgStrip org={org} />}
      {q.isPending || orgs.isPending ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy aria-label="Loading projects">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-40 rounded-[14px]" />
          ))}
        </div>
      ) : q.isError || orgs.isError ? (
        <div className="surface">
          <ErrorState
            error={q.error ?? orgs.error}
            title="Projects could not be loaded"
            onRetry={() => {
              void q.refetch();
              void orgs.refetch();
            }}
          />
        </div>
      ) : projects.length === 0 ? (
        <Onboarding canCreate={canCreate} onCreate={() => setDialog(true)} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {projects.map((p) => (
            <ProjectCard key={p.id} project={p} />
          ))}
        </div>
      )}
      <NewProjectDialog open={open} onOpenChange={setDialog} orgs={orgList.filter((o) => canOrg(o.role, "admin"))} defaultOrg={orgId} />
      <NewOrgDialog open={orgOpen} onOpenChange={setOrgOpen} onCreated={chooseOrg} />
    </>
  );
}

function OrgStrip({ org }: { org: Org }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-5 gap-y-1 rounded-xl bg-muted/70 px-4 py-2.5 text-[12.5px] text-muted-foreground">
      <span className="flex items-center gap-2 font-semibold text-foreground">
        <Building2Icon className="size-4 text-subtle" />
        {org.name}
      </span>
      <Chip tone={org.role === "member" ? "neutral" : "primary"}>{ORG_ROLE_LABEL[org.role ?? "member"]}</Chip>
      <span>{formatNumber(org.projects ?? 0)} projects</span>
      <span>{formatNumber(org.members ?? 0)} members</span>
    </div>
  );
}

const ROLE_TONE = { admin: "primary", editor: "info", viewer: "neutral" } as const;

function ProjectCard({ project: p }: { project: Project }) {
  return (
    <Link
      href={`/projects/${p.id}`}
      className="surface group flex min-w-0 flex-col gap-4 p-5 transition-shadow outline-none hover:shadow-[var(--elev-3)] focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-[15px] font-semibold text-primary">
          {p.name.slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-[15px] font-semibold tracking-[-0.01em]">{p.name}</h2>
            {p.role && <Chip tone={ROLE_TONE[p.role]}>{p.role.charAt(0).toUpperCase() + p.role.slice(1)}</Chip>}
          </div>
          <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-relaxed text-muted-foreground">{p.description || "No description yet."}</p>
        </div>
      </div>
      <div className="mt-auto space-y-3 rounded-xl bg-muted/70 px-4 py-3">
        <div className="grid grid-cols-2 gap-2">
          <Figure label="Tests" value={formatNumber(p.tests ?? 0)} />
          <Figure label="Coverage" value={p.coverage_percent == null ? "None yet" : formatPercent(p.coverage_percent)} />
        </div>
        <CoverageBar percent={p.coverage_percent} />
        <div className="flex items-center justify-between gap-2 text-[11.5px] text-subtle">
          <span>Last run</span>
          <RunStatusChip status={p.last_run_status} />
        </div>
      </div>
      <span className="-mt-1 inline-flex items-center gap-1 self-end text-[12px] font-medium text-primary">
        Open
        <ArrowRightIcon className="size-3 transition-transform group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="truncate text-[10.5px] font-semibold tracking-[0.04em] text-subtle uppercase">{label}</div>
      <div className="tabular truncate text-[20px] leading-tight font-semibold tracking-[-0.02em]">{value}</div>
    </div>
  );
}

const STEPS = [
  { icon: FileCode2Icon, title: "Import your code", body: "A GitHub repository or a ZIP, in Python or JavaScript and TypeScript. Its functions, classes and routes are found for you." },
  { icon: FlaskConicalIcon, title: "Generate real tests", body: "Tests with assertions grounded in the code. A test that could never fail is refused before you see it." },
  { icon: ShieldCheckIcon, title: "Run them safely", body: "Every run is sandboxed: no network, no credentials, fixed limits. You get real coverage and failures explained." },
];

function Onboarding({ onCreate, canCreate }: { onCreate: () => void; canCreate: boolean }) {
  return (
    <div className="surface overflow-hidden">
      <div className="px-6 pt-8 pb-6 text-center sm:px-10">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
          <BrandMark className="size-7" />
        </div>
        <h2 className="text-[19px] font-semibold tracking-[-0.02em]">Tests for your code, written and run safely</h2>
        <p className="mx-auto mt-2 max-w-xl text-[13.5px] leading-relaxed text-muted-foreground">
          TestForge reads your code, writes unit, edge case, negative and API tests that check real values, runs them in an isolated
          sandbox and shows coverage and failures in plain language. Start with a project: it holds one codebase and its test history.
        </p>
      </div>
      <ol className="grid gap-3 px-6 pb-6 sm:px-10 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="rounded-xl bg-muted/70 p-4">
            <div className="flex items-center gap-2.5">
              <span className="flex size-7 items-center justify-center rounded-lg bg-card text-[12px] font-semibold text-primary shadow-[var(--elev-1)]">{i + 1}</span>
              <s.icon className="size-4 text-subtle" aria-hidden />
            </div>
            <div className="mt-3 text-[13.5px] font-semibold">{s.title}</div>
            <p className="mt-1 text-[12.5px] leading-relaxed text-muted-foreground">{s.body}</p>
          </li>
        ))}
      </ol>
      <div className="flex justify-center bg-muted/40 px-6 py-5 text-center">
        {canCreate ? (
          <Button size="lg" onClick={onCreate}>
            <FolderPlusIcon />
            Create your first project
          </Button>
        ) : (
          <p className="max-w-md text-[13px] text-muted-foreground">
            You have no projects in this organization yet. Ask an organization admin to add you to one, or create your own organization.
          </p>
        )}
      </div>
    </div>
  );
}

function NewProjectDialog({
  open,
  onOpenChange,
  orgs,
  defaultOrg,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  orgs: Org[];
  defaultOrg: string;
}) {
  const create = useCreateProject();
  const router = useRouter();
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [orgId, setOrgId] = React.useState(defaultOrg);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setName("");
      setDescription("");
      setError(null);
      setOrgId(orgs.some((o) => o.id === defaultOrg) ? defaultOrg : (orgs[0]?.id ?? ""));
    }
  }, [open, defaultOrg, orgs]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!orgId) return setError("Choose the organization this project belongs to. Only organization admins create projects.");
    if (!name.trim()) return setError("Name the project, for example the service or library it tests.");
    create.mutate(
      { org_id: orgId, name: name.trim(), description: description.trim() },
      {
        onSuccess: (p) => {
          toast.success(`${p.name} is ready. Import its code next.`);
          onOpenChange(false);
          router.push(`/projects/${p.id}?import=1`);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>You become its admin and can add members afterwards.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            {orgs.length > 1 && (
              <Field label="Organization">
                <SimpleSelect aria-label="Organization" value={orgId} onValueChange={setOrgId} options={orgs.map((o) => ({ value: o.id, label: o.name }))} />
              </Field>
            )}
            <Field label="Name" htmlFor="np-name">
              <Input id="np-name" autoFocus maxLength={120} placeholder="Checkout service" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Description" htmlFor="np-desc" hint="Optional. What the code does, and who owns it.">
              <Textarea id="np-desc" maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating..." : "Create project"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function NewOrgDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (open: boolean) => void; onCreated: (id: string) => void }) {
  const create = useCreateOrg();
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setName("");
      setError(null);
    }
  }, [open]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setError("Name the organization, for example your company or team.");
    create.mutate(
      { name: name.trim() },
      {
        onSuccess: (org) => {
          toast.success(`${org.name} is ready. You are its owner.`);
          onOpenChange(false);
          onCreated(org.id);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !create.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New organization</DialogTitle>
          <DialogDescription>An organization groups projects and the people who work in them.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Field label="Name" htmlFor="no-name">
              <Input id="no-name" autoFocus maxLength={120} placeholder="Acme Labs" value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              <PlusIcon />
              {create.isPending ? "Creating..." : "Create organization"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
