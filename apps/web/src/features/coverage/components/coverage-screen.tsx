"use client";

import { PercentIcon, PlayIcon } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { CoverageChart } from "@/components/charts/coverage-chart";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { Stat } from "@/components/stat";
import { CoverageBar } from "@/components/status-chips";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCurrentProject } from "@/features/projects/api";
import { useProjectCoverage, useRunCoverage } from "@/features/runs/api";
import type { Coverage } from "@/lib/api/types";
import { formatRanges, readCoverageFiles } from "@/lib/code";
import { formatDateTime, formatNumber, formatPercent, shortId } from "@/lib/format";

/** Coverage files sorted with the least covered first, the ones to look at. */
export function filesByNeed(cov: Coverage | null | undefined) {
  return readCoverageFiles(cov?.files)
    .filter((f) => f.linesTotal > 0)
    .sort((a, b) => a.percent - b.percent || a.path.localeCompare(b.path));
}

export function CoverageScreen() {
  const { pid, canRun } = useCurrentProject();
  const params = useSearchParams();
  const runId = params.get("run");
  const project = useProjectCoverage(pid);
  const run = useRunCoverage(pid, runId, !!runId);
  const cov = runId ? run.data : project.data?.latest;
  const loading = runId ? run.isPending : project.isPending;
  const error = runId ? run.error : project.error;
  const files = filesByNeed(cov);
  const trend = project.data?.trend ?? [];

  return (
    <>
      <PageHeader
        title="Coverage"
        description={
          runId ? (
            <>
              Line coverage of run {shortId(runId)}, measured inside the sandbox.{" "}
              <Link href={`/projects/${pid}/coverage`} className="font-medium text-primary hover:underline">
                Show the latest
              </Link>
            </>
          ) : (
            "Real line coverage from the latest run, measured by coverage.py or Istanbul inside the sandbox, and how it changed over time."
          )
        }
        actions={
          runId ? (
            <Button variant="outline" nativeButton={false} render={<Link href={`/projects/${pid}/runs/${runId}`} />}>
              Open the run
            </Button>
          ) : undefined
        }
      />
      {loading ? (
        <Skeleton className="h-96 rounded-[14px]" />
      ) : error && !cov ? (
        <div className="surface">
          <ErrorState error={error} title="Coverage could not be loaded" onRetry={() => void (runId ? run.refetch() : project.refetch())} />
        </div>
      ) : !cov ? (
        <Surface>
          <EmptyState
            icon={PercentIcon}
            title="No coverage measured yet"
            description="Run the tests and the sandbox measures which lines of your code they executed. Coverage is never estimated."
            action={
              canRun ? (
                <Button nativeButton={false} render={<Link href={`/projects/${pid}/runs?start=1`} />}>
                  <PlayIcon />
                  Start a run
                </Button>
              ) : undefined
            }
          />
        </Surface>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Line coverage" icon={PercentIcon} value={formatPercent(cov.line_percent)} tone={cov.line_percent >= 80 ? "good" : cov.line_percent < 50 ? "warn" : "default"} detail={`${formatNumber(cov.lines_covered)} of ${formatNumber(cov.lines_total)} lines`} />
            <Stat label="Branch coverage" value={cov.branch_percent == null ? "Not measured" : formatPercent(cov.branch_percent)} detail={cov.branches_total ? `${cov.branches_covered} of ${cov.branches_total} branches` : "Branch data not reported"} />
            <Stat label="Files measured" value={formatNumber(files.length)} detail={`${files.filter((f) => f.percent < 100).length} with missing lines`} />
            <Stat label="Measured by" value={cov.tool} detail={formatDateTime(cov.created_at)} />
          </div>
          {!runId && (
            <Surface className="mt-4">
              <SurfaceHeader
                title={
                  <span className="inline-flex items-center gap-1.5">
                    Coverage over time <Hint term="coverage" />
                  </span>
                }
                description="Line coverage after each run that measured it."
              />
              <div className="px-5 pb-5">
                {trend.length ? (
                  <CoverageChart points={trend.map((t) => ({ at: t.created_at, percent: t.line_percent, runId: t.run_id }))} />
                ) : (
                  <p className="text-[13px] text-muted-foreground">One point so far. Each new run adds one.</p>
                )}
              </div>
            </Surface>
          )}
          <Surface className="mt-4 overflow-hidden">
            <SurfaceHeader title="By file" description="Least covered first. Missing lines are the ones no test executed." />
            {!files.length ? (
              <TableSkeleton rows={2} cols={3} />
            ) : (
              <Table data-qa="coverage-files">
                <TableHeader>
                  <TableRow>
                    <TableHead>File</TableHead>
                    <TableHead className="w-40">Covered</TableHead>
                    <TableHead className="hidden md:table-cell">Missing lines</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {files.map((f) => (
                    <TableRow key={f.path}>
                      <TableCell className="max-w-0">
                        <Link
                          href={`/projects/${pid}/source?file=${encodeURIComponent(f.path)}${cov.import_id ? `&import=${cov.import_id}` : ""}`}
                          className="block truncate font-mono text-[12.5px] hover:text-primary hover:underline"
                        >
                          {f.path}
                        </Link>
                        <div className="text-[11.5px] text-subtle md:hidden">Missing: {formatRanges(f.missing, 3)}</div>
                      </TableCell>
                      <TableCell>
                        <div className="tabular text-[12.5px] font-medium">
                          {formatPercent(f.percent)} <span className="font-normal text-subtle">({f.linesCovered}/{f.linesTotal})</span>
                        </div>
                        <CoverageBar percent={f.percent} className="mt-1" />
                      </TableCell>
                      <TableCell className="hidden font-mono text-[12px] text-muted-foreground md:table-cell">{formatRanges(f.missing)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Surface>
        </>
      )}
    </>
  );
}
