"use client";

import { DownloadIcon, FileTextIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { Segmented } from "@/components/segmented";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Field, FieldError } from "@/components/ui/label";
import { SimpleSelect } from "@/components/ui/select";
import { useCurrentProject } from "@/features/projects/api";
import { useRuns } from "@/features/runs/api";
import { runCounts } from "@/features/runs/components/run-row";
import { errorMessage } from "@/lib/api/errors";
import { formatBytes, formatRelative } from "@/lib/format";
import { runStatusText } from "@/lib/status";

import { useCreateReport, useDownloadReport, useReports } from "../api";

type Scope = "project" | "run";
type Format = "html" | "csv";

export function ReportsScreen() {
  const { pid } = useCurrentProject();
  const q = useReports(pid);
  const runs = useRuns(pid);
  const create = useCreateReport(pid);
  const dl = useDownloadReport(pid);
  const [scope, setScope] = React.useState<Scope>("project");
  const [format, setFormat] = React.useState<Format>("html");
  const [runId, setRunId] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const finished = (runs.data ?? []).filter((r) => r.status !== "queued" && r.status !== "running");
  const list = q.data ?? [];

  function generate(e: React.FormEvent) {
    e.preventDefault();
    const run = runId || finished[0]?.id;
    if (scope === "run" && !run) return setError("There is no finished run yet. Start one first.");
    setError(null);
    create.mutate(
      { scope, format, run_id: scope === "run" ? run : null },
      {
        onSuccess: (r) => {
          toast.success(`${r.title} is ready.`);
          dl.mutate(r, { onError: (err) => toast.error(errorMessage(err)) });
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <>
      <PageHeader title="Reports" description="Share results outside TestForge: one run, or the whole project with its runs, coverage and tests, as HTML to read or CSV to analyze." />
      <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Surface className="self-start">
          <SurfaceHeader title="New report" />
          <form onSubmit={generate} className="space-y-4 px-5 pb-5" noValidate>
            <Field label="Scope">
              <Segmented<Scope>
                ariaLabel="Scope"
                value={scope}
                onChange={setScope}
                options={[
                  { value: "project", label: "Project" },
                  { value: "run", label: "One run" },
                ]}
              />
            </Field>
            {scope === "run" && (
              <Field label="Run">
                <SimpleSelect
                  aria-label="Run"
                  value={runId || finished[0]?.id || ""}
                  onValueChange={setRunId}
                  placeholder="No finished runs"
                  options={finished.map((r) => ({ value: r.id, label: `${runStatusText(r.status, r.limit_exceeded)}: ${runCounts(r)}, ${formatRelative(r.created_at)}` }))}
                />
              </Field>
            )}
            <Field label="Format">
              <Segmented<Format>
                ariaLabel="Format"
                value={format}
                onChange={setFormat}
                options={[
                  { value: "html", label: "HTML" },
                  { value: "csv", label: "CSV" },
                ]}
              />
            </Field>
            {error && <FieldError>{error}</FieldError>}
            <Button type="submit" className="w-full" disabled={create.isPending}>
              <FileTextIcon />
              {create.isPending ? "Generating..." : "Generate and download"}
            </Button>
          </form>
        </Surface>
        <Surface className="overflow-hidden">
          <SurfaceHeader title="Generated reports" description="Every report stays here to download again." />
          {q.isPending ? (
            <TableSkeleton rows={4} cols={3} />
          ) : q.isError ? (
            <ErrorState compact error={q.error} onRetry={() => void q.refetch()} />
          ) : !list.length ? (
            <EmptyState compact icon={FileTextIcon} title="No reports yet" description="Generate one on the left. HTML opens in any browser; CSV opens in a spreadsheet." />
          ) : (
            <ul className="divide-y divide-hairline px-5 pb-3" data-qa="reports">
              {list.map((r) => (
                <li key={r.id} className="flex items-center gap-3 py-2.5">
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-[13.5px] font-medium">{r.title}</span>
                      <Chip tone="neutral">{r.format.toUpperCase()}</Chip>
                    </span>
                    <span className="block text-[12px] text-subtle">
                      {r.scope === "run" ? "One run" : "Project"}, {formatBytes(r.size_bytes)}, {formatRelative(r.created_at)}
                    </span>
                  </span>
                  <Button variant="outline" size="sm" onClick={() => dl.mutate(r, { onError: (err) => toast.error(errorMessage(err)) })} aria-label={`Download ${r.title}`}>
                    <DownloadIcon />
                    <span className="hidden sm:inline">Download</span>
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>
    </>
  );
}
