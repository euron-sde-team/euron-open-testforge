import { ArrowRightIcon } from "lucide-react";
import Link from "next/link";

import { RunStatusChip } from "@/components/status-chips";
import type { Run } from "@/lib/api/types";
import { formatDuration, formatPercent, formatRelative, plural } from "@/lib/format";
import { runKindLabel } from "@/lib/status";

/** "28 passed, 1 failed" from a run's counts, leaving out the zeros. */
export function runCounts(r: Pick<Run, "passed" | "failed" | "errors" | "skipped">): string {
  const parts = [
    r.passed ? `${r.passed} passed` : "",
    r.failed ? `${r.failed} failed` : "",
    r.errors ? plural(r.errors, "error") : "",
    r.skipped ? `${r.skipped} skipped` : "",
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "No test results";
}

/** One run in a list: status, what ran, who started it and when. */
export function RunRow({ pid, run: r }: { pid: string; run: Run }) {
  return (
    <Link
      href={`/projects/${pid}/runs/${r.id}`}
      className="flex items-center gap-3 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
      data-qa="run-row"
    >
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <RunStatusChip status={r.status} limit={r.limit_exceeded} />
          <span className="truncate text-[13.5px] font-medium">{runCounts(r)}</span>
        </span>
        <span className="mt-0.5 block truncate text-[12px] text-subtle">
          {runKindLabel(r.kind)}, {r.actor}, {formatRelative(r.created_at)}
          {r.wall_ms != null ? `, ${formatDuration(r.wall_ms)}` : ""}
          {r.coverage_percent != null ? `, ${formatPercent(r.coverage_percent)} covered` : ""}
        </span>
      </span>
      <ArrowRightIcon className="size-3.5 shrink-0 text-faint" />
    </Link>
  );
}
