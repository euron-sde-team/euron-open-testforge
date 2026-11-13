"use client";

import { Building2Icon, CheckIcon, ChevronsUpDownIcon, FolderPlusIcon, LayoutGridIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import * as React from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useOrgs } from "@/features/orgs/api";
import { useProjects } from "@/features/projects/api";
import { cn } from "@/lib/cn";
import { projectIdFrom } from "@/lib/nav";
import { useUiPrefs } from "@/lib/store";

import { useNavProjectId } from "./use-nav-project";

/**
 * The current organization and project, and a menu to switch: projects are grouped by
 * organization, so switching organization is choosing one of its projects.
 */
export function ProjectSwitcher({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const pathPid = projectIdFrom(pathname);
  const pid = useNavProjectId();
  const { data: projects } = useProjects();
  const { data: orgs } = useOrgs();
  const setLast = useUiPrefs((s) => s.setLastProject);
  const setLastOrg = useUiPrefs((s) => s.setLastOrg);
  const current = projects?.find((p) => p.id === pid);
  const currentOrg = orgs?.find((o) => o.id === current?.org_id);

  React.useEffect(() => {
    if (pathPid) setLast(pathPid);
  }, [pathPid, setLast]);
  React.useEffect(() => {
    if (current?.org_id) setLastOrg(current.org_id);
  }, [current?.org_id, setLastOrg]);

  if (!projects) return <div className="h-12 animate-pulse rounded-xl bg-accent/60" aria-hidden />;
  if (!projects.length) {
    return (
      <Link
        href="/projects"
        onClick={onNavigate}
        className="flex h-11 items-center gap-2 rounded-xl bg-card px-3 text-[13px] font-medium text-primary shadow-[var(--elev-1)] hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
      >
        <FolderPlusIcon className="size-4" />
        {!collapsed && "Create a project"}
      </Link>
    );
  }
  const letter = (current?.name ?? "?").slice(0, 1).toUpperCase();
  const groups = (orgs ?? []).map((o) => ({ org: o, items: projects.filter((p) => p.org_id === o.id) })).filter((g) => g.items.length);
  const orphans = projects.filter((p) => !(orgs ?? []).some((o) => o.id === p.org_id));
  const go = (href: string) => {
    onNavigate?.();
    router.push(href);
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label="Switch project or organization"
        className={cn(
          "flex h-12 w-full items-center gap-2.5 rounded-xl bg-card px-2 text-left shadow-[var(--elev-1)] outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring dark:bg-accent/60",
          collapsed && "h-11 justify-center px-0",
        )}
      >
        {current ? (
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-[13px] font-semibold text-primary-foreground">{letter}</span>
        ) : (
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
            <LayoutGridIcon className="size-3.5" />
          </span>
        )}
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[11px] font-medium text-muted-foreground">{currentOrg?.name ?? (current ? "Project" : `${projects.length} projects`)}</span>
              <span className="block truncate text-[13px] font-semibold text-foreground">{current?.name ?? "Choose a project"}</span>
            </span>
            <ChevronsUpDownIcon className="size-3.5 shrink-0 text-subtle" />
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent className="max-h-[70vh] w-72 overflow-y-auto" align="start">
        {groups.map((g, gi) => (
          <React.Fragment key={g.org.id}>
            {gi > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="flex items-center gap-1.5">
              <Building2Icon className="size-3.5" />
              <span className="truncate">{g.org.name}</span>
            </DropdownMenuLabel>
            {g.items.map((p) => (
              <ProjectItem key={p.id} name={p.name} active={p.id === pid} onClick={() => go(`/projects/${p.id}`)} />
            ))}
          </React.Fragment>
        ))}
        {orphans.length > 0 && (
          <>
            {groups.length > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel>Projects</DropdownMenuLabel>
            {orphans.map((p) => (
              <ProjectItem key={p.id} name={p.name} active={p.id === pid} onClick={() => go(`/projects/${p.id}`)} />
            ))}
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => go("/projects")}>
          <LayoutGridIcon />
          All projects and organizations
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => go("/projects?new=1")}>
          <FolderPlusIcon />
          New project
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ProjectItem({ name, active, onClick }: { name: string; active: boolean; onClick: () => void }) {
  return (
    <DropdownMenuItem onClick={onClick}>
      <span className="flex size-5 items-center justify-center rounded-md bg-primary-soft text-[10px] font-semibold text-primary">{name.slice(0, 1).toUpperCase()}</span>
      <span className="flex-1 truncate">{name}</span>
      {active && <CheckIcon className="size-3.5 text-primary" />}
    </DropdownMenuItem>
  );
}
