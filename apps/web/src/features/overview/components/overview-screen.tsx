"use client";

import { ArrowRightIcon, BanIcon, FileCode2Icon, FlaskConicalIcon, GitBranchIcon, PercentIcon, PlayIcon, TrendingUpIcon, UploadIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { CoverageChart } from "@/components/charts/coverage-chart";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { RoleNote } from "@/components/role-note";
import { Stat } from "@/components/stat";
import { ImportStatusChip, SandboxBadge } from "@/components/status-chips";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { ImportDialog } from "@/features/imports/components/import-dialog";
import { useCurrentProject } from "@/features/projects/api";
import { RunRow } from "@/features/runs/components/run-row";
import { StartRunDialog } from "@/features/runs/components/start-run-dialog";
import type { Overview } from "@/lib/api/types";
import { readCounts } from "@/lib/failure";
import { formatNumber, formatPercent, formatRelative, plural, shortSha } from "@/lib/format";
import { nextStep } from "@/lib/next-step";
import { frameworkLabel, languageLabel } from "@/lib/status";

import { useOverview } from "../api";

export function OverviewScreen() {
  const { pid, project, canImport, canRun } = useCurrentProject();
  const q = useOverview(pid);
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [importing, setImporting] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const d = q.data;

  React.useEffect(() => {
    if (params.get("import") === "1" && canImport) setImporting(true);
  }, [params, canImport]);

  function setImport(open: boolean) {
    setImporting(open);
    if (!open && params.get("import")) router.replace(pathname, { scroll: false });
  }

  const tests = readCounts(d?.tests);
  const hasCode = !!d?.current_import;

  return (
    <>
      <PageHeader
        title={project?.name ?? "Overview"}
        description={project?.description || "This project's code, its generated tests, the runs in the sandbox and their coverage."}
        actions={
          <>
            {canImport && (
              <Button variant="outline" onClick={() => setImport(true)}>
                <UploadIcon />
                Import code
              </Button>
            )}
            {canRun && hasCode && (
              <Button onClick={() => setRunning(true)}>
                <PlayIcon />
                Run tests
              </Button>
            )}
          </>
        }
      />
      {!canImport && project && <RoleNote className="mb-4">You can read everything in this project. Editors and admins import code, generate tests and start runs.</RoleNote>}
      {q.isError ? (
        <div className="surface">
          <ErrorState error={q.error} title="The overview could not be loaded" onRetry={() => void q.refetch()} />
        </div>
      ) : d && !hasCode ? (
        <Surface>
          <EmptyState
            icon={FileCode2Icon}
            title="No code imported yet"
            description="Import a GitHub repository or a ZIP of a Python or JavaScript and TypeScript project. TestForge finds its functions, classes and routes, and which of them no test touches."
            action={
              canImport ? (
                <Button onClick={() => setImport(true)}>
                  <UploadIcon />
                  Import code
                </Button>
              ) : (
                <span className="text-[12.5px] text-muted-foreground">An editor or admin of this project imports the code.</span>
              )
            }
          />
        </Surface>
      ) : (
        <>
          {d && canImport && <NextStepBanner pid={pid} d={d} tests={tests} onImport={() => setImport(true)} onRun={() => setRunning(true)} />}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label="Tests"
              icon={FlaskConicalIcon}
              loading={!d}
              value={formatNumber(tests.accepted ?? 0)}
              detail={d ? `accepted, ${formatNumber(tests.proposed ?? 0)} waiting for review` : undefined}
            />
            <Stat
              label="Refused tests"
              icon={BanIcon}
              loading={!d}
              value={d ? formatNumber(d.rejected_tests) : ""}
              detail={
                <span className="inline-flex items-center gap-1">
                  No meaningful assertion <Hint term="refused" />
                </span>
              }
            />
            <Stat
              label="Pass rate"
              icon={TrendingUpIcon}
              loading={!d}
              value={d?.pass_rate == null ? "No runs yet" : formatPercent(d.pass_rate)}
              tone={d?.pass_rate != null && d.pass_rate >= 80 ? "good" : "default"}
              detail={d ? runsByStatusText(d) : undefined}
            />
            <Stat
              label="Coverage"
              icon={PercentIcon}
              loading={!d}
              value={d?.coverage_percent == null ? "None yet" : formatPercent(d.coverage_percent)}
              tone={d?.coverage_percent != null && d.coverage_percent >= 80 ? "good" : d?.coverage_percent != null && d.coverage_percent < 50 ? "warn" : "default"}
              detail={d ? <Link href={`/projects/${pid}/source?tab=units&untested=1`} className="hover:text-foreground hover:underline">{plural(d.untested_units, "unit")} not tested</Link> : undefined}
            />
          </div>

          <div className="mt-4 grid min-w-0 gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Surface>
              <SurfaceHeader
                title={
                  <span className="inline-flex items-center gap-1.5">
                    Coverage over time <Hint term="coverage" />
                  </span>
                }
                description="Line coverage measured in the sandbox, after each run."
                action={
                  <Link href={`/projects/${pid}/coverage`} className="text-[12.5px] font-medium text-primary hover:underline">
                    Coverage
                  </Link>
                }
              />
              <div className="px-5 pb-5">
                {!d ? (
                  <Skeleton className="h-[220px] w-full" />
                ) : d.coverage_trend.length ? (
                  <CoverageChart points={d.coverage_trend.map((p) => ({ at: p.at, percent: p.percent, runId: p.run_id }))} />
                ) : (
                  <EmptyState compact icon={PercentIcon} title="No coverage yet" description="Run the tests and the coverage of each run is plotted here, from coverage.py or Istanbul output." />
                )}
              </div>
            </Surface>
            <Surface>
              <SurfaceHeader title="Current code" action={d?.current_import ? <ImportStatusChip status={d.current_import.status} /> : undefined} />
              <div className="px-5 pb-5">
                {!d?.current_import ? (
                  <Skeleton className="h-40" />
                ) : (
                  <div className="space-y-4">
                    <div>
                      <div className="flex items-center gap-2 text-[14px] font-semibold">
                        <GitBranchIcon className="size-4 text-subtle" />
                        <span className="truncate">{d.current_import.repo ?? d.current_import.label}</span>
                      </div>
                      <div className="mt-0.5 text-[12px] text-subtle">
                        {d.current_import.ref ? `${d.current_import.ref}, ` : ""}
                        {d.current_import.commit_sha ? `commit ${shortSha(d.current_import.commit_sha)}, ` : ""}
                        imported {formatRelative(d.current_import.created_at)}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {d.current_import.languages.map((l) => (
                        <Chip key={l} tone="primary">
                          {languageLabel(l)}
                        </Chip>
                      ))}
                      {[...d.current_import.frameworks, ...d.current_import.test_frameworks].map((f) => (
                        <Chip key={f} tone="neutral">
                          {frameworkLabel(f)}
                        </Chip>
                      ))}
                    </div>
                    <dl className="grid grid-cols-3 gap-2 rounded-xl bg-muted/70 px-4 py-3">
                      <Fig label="Units" value={formatNumber(d.units)} />
                      <Fig label="Untested" value={formatNumber(d.untested_units)} />
                      <Fig label="Files" value={formatNumber(d.current_import.file_count)} />
                    </dl>
                    <Link href={`/projects/${pid}/source`} className="inline-flex items-center gap-1 text-[12.5px] font-medium text-primary hover:underline">
                      Explore the source <ArrowRightIcon className="size-3" />
                    </Link>
                  </div>
                )}
              </div>
            </Surface>
          </div>

          <Surface className="mt-4">
            <SurfaceHeader
              title="Recent runs"
              titleExtra={<SandboxBadge className="ml-1.5 hidden sm:inline-flex" />}
              action={
                <Link href={`/projects/${pid}/runs`} className="text-[12.5px] font-medium text-primary hover:underline">
                  All runs
                </Link>
              }
            />
            <div className="px-3 pb-3">
              {!d ? (
                <Skeleton className="mx-2 h-40" />
              ) : !d.recent_runs.length ? (
                <EmptyState
                  compact
                  icon={PlayIcon}
                  title="No runs yet"
                  description="A run executes tests in the sandbox and reports pass or fail, coverage and every failure explained."
                  action={
                    canRun ? (
                      <Button size="sm" onClick={() => setRunning(true)}>
                        Run tests
                      </Button>
                    ) : undefined
                  }
                />
              ) : (
                <ul className="space-y-0.5">
                  {d.recent_runs.map((r) => (
                    <li key={r.id}>
                      <RunRow pid={pid} run={r} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Surface>
        </>
      )}
      {canImport && <ImportDialog pid={pid} open={importing} onOpenChange={setImport} defaultRepo={project?.github_repo} />}
      {canRun && <StartRunDialog pid={pid} open={running} onOpenChange={setRunning} />}
    </>
  );
}

function runsByStatusText(d: Overview): string {
  const by = readCounts(d.runs_by_status);
  if (!d.runs_total) return "Start a run to see it";
  const parts = Object.entries(by)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${v} ${k.replace("_", " ")}`);
  return `${plural(d.runs_total, "run")}: ${parts.join(", ")}`;
}

function Fig({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[10.5px] font-semibold tracking-[0.04em] text-subtle uppercase">{label}</dt>
      <dd className="tabular text-[18px] font-semibold">{value}</dd>
    </div>
  );
}

function NextStepBanner({
  pid,
  d,
  tests,
  onImport,
  onRun,
}: {
  pid: string;
  d: Overview;
  tests: Record<string, number>;
  onImport: () => void;
  onRun: () => void;
}) {
  const step = nextStep({
    importStatus: d.current_import?.status,
    untested: d.untested_units,
    proposed: tests.proposed ?? 0,
    accepted: tests.accepted ?? 0,
    runsTotal: d.runs_total,
    latestStatus: d.latest_run?.status,
    coverage: d.coverage_percent,
  });
  if (step.id === "done") return null;
  const action =
    step.id === "import" ? (
      <Button size="sm" onClick={onImport}>
        {step.action}
      </Button>
    ) : step.id === "run" ? (
      <Button size="sm" onClick={onRun}>
        {step.action}
      </Button>
    ) : (
      <Button size="sm" nativeButton={false} render={<Link href={`/projects/${pid}${step.id === "fix" && d.latest_run ? `/runs/${d.latest_run.id}` : step.href}`} />}>
        {step.action}
      </Button>
    );
  return (
    <div className="mb-4 flex flex-col gap-3 rounded-[14px] bg-primary-soft px-5 py-4 sm:flex-row sm:items-center sm:justify-between" data-qa="next-step">
      <div className="min-w-0">
        <div className="text-[11px] font-semibold tracking-[0.06em] text-primary uppercase">Next step</div>
        <div className="mt-0.5 text-[14.5px] font-semibold text-foreground">{step.title}</div>
        <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted-foreground">{step.body}</p>
      </div>
      <div className="shrink-0">{action}</div>
    </div>
  );
}
