import {
  BanIcon,
  CheckCircle2Icon,
  CircleDashedIcon,
  CircleSlashIcon,
  GaugeIcon,
  Loader2Icon,
  ShieldCheckIcon,
  TriangleAlertIcon,
  XCircleIcon,
  type LucideIcon,
} from "lucide-react";

import { Chip } from "@/components/ui/chip";
import { cn } from "@/lib/cn";
import {
  coverageTone,
  generationLabel,
  generationTone,
  importLabel,
  importTone,
  outcomeLabel,
  outcomeTone,
  runStatusText,
  runTone,
  testKindLabel,
  testStatusLabel,
  testStatusTone,
} from "@/lib/status";
import { formatPercent } from "@/lib/format";

const RUN_ICON: Record<string, LucideIcon> = {
  queued: CircleDashedIcon,
  running: Loader2Icon,
  passed: CheckCircle2Icon,
  failed: XCircleIcon,
  error: TriangleAlertIcon,
  limit_exceeded: GaugeIcon,
};

/** A run's state: icon, word and tone together, never color alone. Names the limit it crossed. */
export function RunStatusChip({ status, limit, className }: { status: string | null | undefined; limit?: string | null; className?: string }) {
  const Icon = (status && RUN_ICON[status]) || CircleDashedIcon;
  return (
    <Chip tone={runTone(status)} className={className} data-qa="run-status">
      <Icon className={cn(status === "running" && "animate-spin")} aria-hidden />
      {runStatusText(status, limit)}
    </Chip>
  );
}

const OUTCOME_ICON: Record<string, LucideIcon> = {
  passed: CheckCircle2Icon,
  failed: XCircleIcon,
  error: TriangleAlertIcon,
  skipped: CircleSlashIcon,
};

export function OutcomeChip({ outcome, className }: { outcome: string | null | undefined; className?: string }) {
  const Icon = (outcome && OUTCOME_ICON[outcome]) || CircleDashedIcon;
  return (
    <Chip tone={outcomeTone(outcome)} className={className}>
      <Icon aria-hidden />
      {outcomeLabel(outcome)}
    </Chip>
  );
}

export function TestStatusChip({ status, className }: { status: string; className?: string }) {
  const Icon = status === "accepted" ? CheckCircle2Icon : status === "discarded" ? BanIcon : CircleDashedIcon;
  return (
    <Chip tone={testStatusTone(status)} className={className}>
      <Icon aria-hidden />
      {testStatusLabel(status)}
    </Chip>
  );
}

export function TestKindChip({ kind, className }: { kind: string; className?: string }) {
  return (
    <Chip tone="neutral" className={className}>
      {testKindLabel(kind)}
    </Chip>
  );
}

export function ImportStatusChip({ status, className }: { status: string; className?: string }) {
  const Icon = status === "ready" ? CheckCircle2Icon : status === "failed" ? XCircleIcon : Loader2Icon;
  return (
    <Chip tone={importTone(status)} className={className}>
      <Icon className={cn((status === "pending" || status === "analyzing") && "animate-spin")} aria-hidden />
      {importLabel(status)}
    </Chip>
  );
}

export function GenerationStatusChip({ status, className }: { status: string; className?: string }) {
  const Icon = status === "done" ? CheckCircle2Icon : status === "failed" ? XCircleIcon : Loader2Icon;
  return (
    <Chip tone={generationTone(status)} className={className}>
      <Icon className={cn((status === "queued" || status === "running") && "animate-spin")} aria-hidden />
      {generationLabel(status)}
    </Chip>
  );
}

export function CoverageChip({ percent, className }: { percent: number | null | undefined; className?: string }) {
  return (
    <Chip tone={coverageTone(percent)} className={cn("tabular", className)}>
      {percent == null ? "No coverage yet" : `${formatPercent(percent)} covered`}
    </Chip>
  );
}

/** The promise every run keeps, shown wherever a run is. */
export function SandboxBadge({ className }: { className?: string }) {
  return (
    <Chip tone="success" className={className} data-qa="sandbox-badge">
      <ShieldCheckIcon aria-hidden />
      Sandboxed: no network, no credentials
    </Chip>
  );
}

/** A coverage bar: a fill whose width is the percentage, toned by how good it is. */
export function CoverageBar({ percent, className }: { percent: number | null | undefined; className?: string }) {
  const tone = coverageTone(percent);
  const width = percent == null ? 0 : Math.max(0, Math.min(100, percent));
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent ?? 0}
      aria-label="Coverage"
    >
      <div
        className={cn(
          "h-full rounded-full",
          tone === "success" && "bg-savings",
          tone === "warning" && "bg-warning",
          tone === "danger" && "bg-danger",
          tone === "neutral" && "bg-faint",
        )}
        style={{ width: `${width}%` }}
      />
    </div>
  );
}
