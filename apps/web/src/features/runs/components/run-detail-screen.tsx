"use client";

import {
  ArrowLeftIcon,
  CpuIcon,
  GaugeIcon,
  GlobeLockIcon,
  KeyRoundIcon,
  Loader2Icon,
  PercentIcon,
  PlayIcon,
  ShieldCheckIcon,
  SparklesIcon,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { CodeBlock } from "@/components/code-block";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { OutcomeChip, RunStatusChip } from "@/components/status-chips";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentProject } from "@/features/projects/api";
import { ApiError, errorMessage } from "@/lib/api/errors";
import type { RunDetail, TestCase } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { failureTitle, hasComparison, operatorWords, readFailure, readLimits, refusalText, sandboxRefusal, type Refusal } from "@/lib/failure";
import { formatBytes, formatDateTime, formatDuration, formatMemoryKb, formatPercent, formatSeconds, plural } from "@/lib/format";
import { frameworkLabel, inFlight, languageLabel, limitExplanation, limitLabel, runKindLabel } from "@/lib/status";

import { useExplainWithModel, useRun } from "../api";

import { runCounts } from "./run-row";

export function RunDetailScreen() {
  const { pid, canGenerate } = useCurrentProject();
  const { rid } = useParams<{ rid: string }>();
  const q = useRun(pid, rid);
  const r = q.data;
  const back = (
    <Link href={`/projects/${pid}/runs`} className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-3.5" /> Runs
    </Link>
  );

  if (q.isPending) {
    return (
      <>
        <PageHeader eyebrow={back} title={<Skeleton className="h-7 w-64" />} />
        <Skeleton className="h-96 rounded-[14px]" />
      </>
    );
  }
  if (q.isError || !r) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <>
        <PageHeader eyebrow={back} title="Run" />
        <Surface>
          {missing ? (
            <EmptyState icon={PlayIcon} title="This run does not exist" description="It may belong to another project. Open one from the list of runs." />
          ) : (
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          )}
        </Surface>
      </>
    );
  }

  const cases = r.cases ?? [];
  const failures = cases.filter((c) => c.outcome === "failed" || c.outcome === "error");
  const running = inFlight(r.status);
  return (
    <>
      <PageHeader
        eyebrow={back}
        title={
          <span className="flex flex-wrap items-center gap-3">
            {runKindLabel(r.kind)}
            <RunStatusChip status={r.status} limit={r.limit_exceeded} className="h-6 px-2.5 text-[12px]" />
          </span>
        }
        description={`${running ? "Started" : runCounts(r)}. ${languageLabel(r.language)} with ${frameworkLabel(r.framework)}, started by ${r.actor} (${r.trigger}) on ${formatDateTime(r.created_at)}.`}
        actions={
          r.coverage_percent != null ? (
            <Button variant="outline" nativeButton={false} render={<Link href={`/projects/${pid}/coverage?run=${r.id}`} />}>
              <PercentIcon />
              Coverage {formatPercent(r.coverage_percent)}
            </Button>
          ) : undefined
        }
      />
      <SandboxNote />
      {r.status === "limit_exceeded" && <LimitBanner run={r} />}
      <RefusalSummary cases={cases} />
      {running ? (
        <Surface className="mt-4">
          <div className="flex items-center gap-3 px-5 py-8 text-[13.5px]" aria-live="polite">
            <Loader2Icon className="size-5 animate-spin text-primary" />
            {r.status === "queued" ? "Waiting for a sandbox." : "Running in the sandbox. Results appear here when it finishes."}
          </div>
        </Surface>
      ) : (
        <>
          <Measurements run={r} />
          {failures.length > 0 && (
            <section className="mt-4 space-y-3" aria-labelledby="failures-title">
              <h2 id="failures-title" className="px-1 text-[15px] font-semibold">
                {failures.length === 1 ? "1 failure, explained" : `${failures.length} failures, explained`}
              </h2>
              {failures.map((c) => (
                <FailureCard key={c.id} pid={pid} run={r} c={c} canExplain={canGenerate} />
              ))}
            </section>
          )}
          <CaseList pid={pid} cases={cases} />
          <Surface className="mt-4">
            <SurfaceHeader title="Output" description="The last lines the run printed, as the sandbox captured them." />
            <div className="grid gap-3 px-5 pb-5 lg:grid-cols-2">
              <CodeBlock value={r.stdout_tail || "Nothing printed."} label="stdout" maxLines={18} wrap={false} />
              <CodeBlock value={r.stderr_tail || "Nothing printed."} label="stderr" maxLines={18} wrap={false} />
            </div>
          </Surface>
        </>
      )}
    </>
  );
}

function SandboxNote() {
  return (
    <div className="flex items-start gap-3 rounded-[14px] bg-savings-soft px-5 py-4 text-savings" data-qa="sandbox-note">
      <ShieldCheckIcon className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="text-[13px] leading-relaxed">
        <div className="font-semibold">This run executed in the sandbox</div>
        No network interface, no credentials, no host files: it saw only its own workspace, under fixed CPU, memory, output and time limits.
      </div>
    </div>
  );
}

/** "The sandbox refused 4 attempts to leave the run" when the project's own tests tried. */
function RefusalSummary({ cases }: { cases: TestCase[] }) {
  const counts = { network: 0, file: 0, credentials: 0 };
  for (const c of cases) {
    const r = sandboxRefusal(readFailure(c.failure));
    if (r) counts[r] += 1;
  }
  const total = counts.network + counts.file + counts.credentials;
  if (!total) return null;
  const parts = [
    counts.network ? `${plural(counts.network, "network call")}` : "",
    counts.file ? `${plural(counts.file, "host file read")}` : "",
    counts.credentials ? `${plural(counts.credentials, "credentials lookup")}` : "",
  ].filter(Boolean);
  return (
    <div className="mt-3 flex items-start gap-3 rounded-[14px] bg-card px-5 py-4 shadow-[var(--elev-2)]" data-qa="refusal-summary">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-savings-soft text-savings">
        <GlobeLockIcon className="size-4" aria-hidden />
      </span>
      <div className="text-[13px] leading-relaxed">
        <div className="font-semibold">The sandbox refused {plural(total, "attempt")} to leave this run</div>
        <span className="text-muted-foreground">{parts.join(", ")}. These tests fail because the isolation held, not because of a bug in the code.</span>
      </div>
    </div>
  );
}

function LimitBanner({ run: r }: { run: RunDetail }) {
  return (
    <div role="alert" className="mt-3 flex items-start gap-3 rounded-[14px] bg-warning-soft px-5 py-4 text-warning" data-qa="limit-banner">
      <GaugeIcon className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="text-[13px] leading-relaxed">
        <div className="font-semibold">Limit crossed: {limitLabel(r.limit_exceeded)}</div>
        {r.message ? `${r.message}.`.replace(/\.\.$/, ".") : limitExplanation(r.limit_exceeded)}
        <div className="mt-1 text-[12px] opacity-90">The sandbox stopped the whole run at the limit; nothing was left running and no output was silently cut.</div>
      </div>
    </div>
  );
}

function Measure({ label, value, of, hot, icon: Icon }: { label: string; value: string; of?: string; hot?: boolean; icon: LucideIcon }) {
  return (
    <div className={cn("rounded-xl bg-muted/70 px-4 py-3", hot && "bg-warning-soft")}>
      <div className={cn("flex items-center gap-1.5 text-[11.5px] font-medium text-muted-foreground", hot && "text-warning")}>
        <Icon className="size-3.5" aria-hidden />
        {label}
      </div>
      <div className={cn("tabular mt-0.5 text-[17px] font-semibold", hot && "text-warning")}>{value}</div>
      {of && <div className="text-[11.5px] text-subtle">of {of}</div>}
    </div>
  );
}

function Measurements({ run: r }: { run: RunDetail }) {
  const l = readLimits(r.limits);
  const hit = r.limit_exceeded;
  return (
    <Surface className="mt-4">
      <SurfaceHeader
        title={
          <span className="inline-flex items-center gap-1.5">
            Sandbox measurements <Hint term="limit" />
          </span>
        }
        description="What the run used, against the limits it had."
      />
      <div className="grid grid-cols-2 gap-2.5 px-5 pb-5 md:grid-cols-3 xl:grid-cols-6" data-qa="measurements">
        <Measure icon={CpuIcon} label="CPU time" value={formatDuration(r.cpu_ms)} of={l.cpu_s != null ? formatSeconds(l.cpu_s) : undefined} hot={hit === "cpu"} />
        <Measure icon={GaugeIcon} label="Wall clock" value={formatDuration(r.wall_ms)} of={l.wall_s != null ? formatSeconds(l.wall_s) : undefined} hot={hit === "wall_clock"} />
        <Measure icon={CpuIcon} label="Peak memory" value={formatMemoryKb(r.memory_kb)} of={l.memory_mb != null ? `${l.memory_mb} MB` : undefined} hot={hit === "memory"} />
        <Measure icon={CpuIcon} label="Output" value={formatBytes(r.output_bytes)} of={l.output_bytes != null ? formatBytes(l.output_bytes) : undefined} hot={hit === "output"} />
        <Measure icon={PlayIcon} label="Exit code" value={r.exit_code != null ? String(r.exit_code) : r.signal != null ? `Signal ${r.signal}` : "n/a"} />
        <Measure icon={PercentIcon} label="Coverage" value={r.coverage_percent != null ? formatPercent(r.coverage_percent) : "Not measured"} />
      </div>
    </Surface>
  );
}

const REFUSAL_ICON: Record<Exclude<Refusal, null>, LucideIcon> = { network: GlobeLockIcon, file: ShieldCheckIcon, credentials: KeyRoundIcon };

function FailureCard({ pid, run, c, canExplain }: { pid: string; run: RunDetail; c: TestCase; canExplain: boolean }) {
  const f = readFailure(c.failure);
  const refusal = sandboxRefusal(f);
  const explain = useExplainWithModel(pid);
  const [modelText, setModelText] = React.useState<string | null>(null);
  const RIcon = refusal ? REFUSAL_ICON[refusal] : null;
  return (
    <Surface data-qa="failure">
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <OutcomeChip outcome={c.outcome} />
            {refusal && RIcon && (
              <Chip tone="success" data-qa="refusal">
                <RIcon aria-hidden />
                {refusalText(refusal).title}
              </Chip>
            )}
            {f?.kind === "limit" ? (
              <Chip tone="warning">
                <GaugeIcon aria-hidden />
                Stopped at the {limitLabel(f.limit).toLowerCase()} limit
              </Chip>
            ) : (
              f && !refusal && <span className="text-[12.5px] font-medium text-muted-foreground">{failureTitle(f)}</span>
            )}
          </div>
          <h3 className="mt-1.5 font-mono text-[13.5px] font-semibold break-all">{c.name}</h3>
          <div className="mt-0.5 font-mono text-[11.5px] break-all text-subtle">
            {c.file}
            {f?.line != null ? `:${f.line}` : ""}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {c.generated_test_id && (
            <Button variant="ghost" size="sm" nativeButton={false} render={<Link href={`/projects/${pid}/tests/${c.generated_test_id}`} />}>
              Open the test
            </Button>
          )}
          {canExplain && !refusal && f?.kind !== "limit" && (
            <Button
              variant="outline"
              size="sm"
              disabled={explain.isPending}
              onClick={() =>
                explain.mutate(
                  { run_id: run.id, case_id: c.id },
                  { onSuccess: (r) => setModelText(r.model_explanation ?? "The model had nothing to add."), onError: (err) => toast.error(errorMessage(err)) },
                )
              }
            >
              <SparklesIcon />
              {explain.isPending ? "Asking..." : "Explain with the model"}
            </Button>
          )}
        </div>
      </div>
      <div className="space-y-3 px-5 pb-5">
        {refusal && <p className="rounded-xl bg-savings-soft px-4 py-3 text-[12.5px] leading-relaxed text-savings">{refusalText(refusal).body}</p>}
        {f && <p className="text-[13.5px] leading-relaxed [overflow-wrap:anywhere]" data-qa="explanation">{f.explanation}</p>}
        {hasComparison(f) && (
          <div className="grid gap-2.5 sm:grid-cols-2" data-qa="comparison">
            <div className="min-w-0 rounded-xl bg-danger-soft px-4 py-3">
              <div className="text-[11px] font-semibold tracking-[0.05em] text-danger uppercase">The code returned (actual)</div>
              <code className="mt-1 block font-mono text-[13px] break-all text-foreground" data-qa="actual">
                {f.actual}
              </code>
            </div>
            <div className="min-w-0 rounded-xl bg-savings-soft px-4 py-3">
              <div className="text-[11px] font-semibold tracking-[0.05em] text-savings uppercase">The test {operatorWords(f.operator)} (expected)</div>
              <code className="mt-1 block font-mono text-[13px] break-all text-foreground" data-qa="expected">
                {f.expected}
              </code>
            </div>
          </div>
        )}
        {f?.expression && (
          <div>
            <div className="mb-1 text-[11.5px] font-medium text-muted-foreground">Failing expression{f.line != null ? `, line ${f.line}` : ""}</div>
            <code className="block rounded-lg bg-code-bg px-3.5 py-2.5 font-mono text-[12.5px] whitespace-pre-wrap text-code-fg [overflow-wrap:anywhere]" data-qa="expression">
              {f.expression}
            </code>
          </div>
        )}
        {modelText && (
          <div className="rounded-xl bg-info-soft px-4 py-3 text-[13px] leading-relaxed" data-qa="model-explanation">
            <div className="mb-1 flex items-center gap-1.5 text-[11.5px] font-semibold text-info">
              <SparklesIcon className="size-3.5" aria-hidden /> From the project&apos;s model
            </div>
            {modelText}
          </div>
        )}
        {f?.message && f.kind !== "assertion" && f.kind !== "limit" && !refusal && <CodeBlock value={f.message} label="Error" maxLines={8} />}
      </div>
    </Surface>
  );
}

function CaseList({ pid, cases }: { pid: string; cases: TestCase[] }) {
  if (!cases.length) {
    return (
      <Surface className="mt-4">
        <EmptyState
          compact
          icon={PlayIcon}
          title="No test results"
          description="The run ended before any test reported a result. The banner above and the output below say why."
        />
      </Surface>
    );
  }
  const order: Record<string, number> = { failed: 0, error: 1, skipped: 2, passed: 3 };
  const sorted = [...cases].sort((a, b) => (order[a.outcome] ?? 9) - (order[b.outcome] ?? 9) || a.nodeid.localeCompare(b.nodeid));
  return (
    <Surface className="mt-4">
      <SurfaceHeader title="Every test case" description={plural(cases.length, "test case")} />
      <ul className="divide-y divide-hairline px-5 pb-3" data-qa="cases">
        {sorted.map((c) => (
          <li key={c.id} className="flex items-center gap-3 py-2">
            <OutcomeChip outcome={c.outcome} className="shrink-0" />
            <span className="min-w-0 flex-1 truncate font-mono text-[12.5px]" title={c.nodeid}>
              {c.generated_test_id ? (
                <Link href={`/projects/${pid}/tests/${c.generated_test_id}`} className="hover:text-primary hover:underline">
                  {c.nodeid}
                </Link>
              ) : (
                c.nodeid
              )}
            </span>
            <span className="tabular shrink-0 text-[11.5px] text-subtle">{formatDuration(c.duration_ms)}</span>
          </li>
        ))}
      </ul>
    </Surface>
  );
}
