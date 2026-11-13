"use client";

import { PlayIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { RoleNote } from "@/components/role-note";
import { SandboxBadge } from "@/components/status-chips";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { SimpleSelect } from "@/components/ui/select";
import { useCurrentProject } from "@/features/projects/api";

import { useRuns } from "../api";

import { RunRow } from "./run-row";
import { StartRunDialog } from "./start-run-dialog";

const STATUSES = [
  { value: "", label: "Every status" },
  { value: "passed", label: "Passed" },
  { value: "failed", label: "Failed" },
  { value: "error", label: "Error" },
  { value: "limit_exceeded", label: "Limit crossed" },
  { value: "running", label: "Running" },
  { value: "queued", label: "Queued" },
];

export function RunsScreen() {
  const { pid, project, canRun } = useCurrentProject();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const status = params.get("status") ?? "";
  const q = useRuns(pid, status);
  const [starting, setStarting] = React.useState(false);
  const noCode = project && !project.current_import_id;
  const list = q.data ?? [];

  React.useEffect(() => {
    if (params.get("start") === "1" && canRun) setStarting(true);
  }, [params, canRun]);

  function setStart(open: boolean) {
    setStarting(open);
    if (!open && params.get("start")) router.replace(pathname, { scroll: false });
  }

  return (
    <>
      <PageHeader
        title="Runs"
        description="Every execution of tests, generated or the project's own, with its result, its resource use and who started it."
        eyebrow={<SandboxBadge />}
        actions={
          <>
            <SimpleSelect
              aria-label="Status"
              className="w-44"
              value={status}
              onValueChange={(v) => router.replace(v ? `${pathname}?status=${v}` : pathname, { scroll: false })}
              options={STATUSES}
            />
            {canRun && !noCode && (
              <Button onClick={() => setStart(true)}>
                <PlayIcon />
                Start a run
              </Button>
            )}
          </>
        }
      />
      {!canRun && project && <RoleNote className="mb-4">You can read every run and its failures. Editors and admins start runs.</RoleNote>}
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={6} cols={3} />
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} title="The runs could not be loaded" onRetry={() => void q.refetch()} />
        ) : !list.length ? (
          status ? (
            <EmptyState
              icon={PlayIcon}
              title="No runs with this status"
              description="Choose another status, or show every run."
              action={
                <Button variant="outline" size="sm" onClick={() => router.replace(pathname, { scroll: false })}>
                  Show every run
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={PlayIcon}
              title="No runs yet"
              description={
                noCode
                  ? "Import the code first. A run then executes its tests in the sandbox and reports results, coverage and failures."
                  : "A run executes tests in a sandbox with no network and no credentials, and reports results, real coverage and every failure explained."
              }
              action={
                canRun ? (
                  noCode ? (
                    <Button nativeButton={false} render={<Link href={`/projects/${pid}?import=1`} />}>
                      Import code
                    </Button>
                  ) : (
                    <Button onClick={() => setStart(true)}>
                      <PlayIcon />
                      Start a run
                    </Button>
                  )
                ) : undefined
              }
            />
          )
        ) : (
          <ul className="space-y-0.5 p-3" data-qa="runs">
            {list.map((r) => (
              <li key={r.id}>
                <RunRow pid={pid} run={r} />
              </li>
            ))}
          </ul>
        )}
      </Surface>
      {canRun && <StartRunDialog pid={pid} open={starting} onOpenChange={setStart} />}
    </>
  );
}
