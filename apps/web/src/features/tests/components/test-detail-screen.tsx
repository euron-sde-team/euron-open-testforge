"use client";

import { ArrowLeftIcon, BanIcon, CheckIcon, FlaskConicalIcon, PlayIcon, RefreshCwIcon, TargetIcon } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { CodeView } from "@/components/code-view";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { OutcomeChip, TestKindChip, TestStatusChip } from "@/components/status-chips";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentProject } from "@/features/projects/api";
import { StartRunDialog } from "@/features/runs/components/start-run-dialog";
import { ApiError, errorMessage } from "@/lib/api/errors";
import type { TestDetail } from "@/lib/api/types";
import { formatRelative, plural } from "@/lib/format";
import { frameworkLabel, languageLabel, unitKindLabel } from "@/lib/status";

import { useRegenerate, useReviewTest, useTest } from "../api";

import { GenerationResult } from "./generate-dialog";

interface UnitRef {
  qualname: string;
  kind: string;
  file: string;
  start_line: number;
  end_line: number;
  signature: string;
  source: string;
}

/** The unit a test is for, as the test detail carries it. */
export function readUnit(raw: unknown): UnitRef | null {
  if (typeof raw !== "object" || raw === null) return null;
  const u = raw as Record<string, unknown>;
  if (typeof u.qualname !== "string") return null;
  return {
    qualname: u.qualname,
    kind: typeof u.kind === "string" ? u.kind : "function",
    file: typeof u.file === "string" ? u.file : "",
    start_line: typeof u.start_line === "number" ? u.start_line : 1,
    end_line: typeof u.end_line === "number" ? u.end_line : 1,
    signature: typeof u.signature === "string" ? u.signature : "",
    source: typeof u.source === "string" ? u.source : "",
  };
}

export function TestDetailScreen() {
  const { pid, canReview, canRun } = useCurrentProject();
  const { tid } = useParams<{ tid: string }>();
  const q = useTest(pid, tid);
  const review = useReviewTest(pid);
  const regen = useRegenerate(pid);
  const [running, setRunning] = React.useState(false);
  const [generationId, setGenerationId] = React.useState<string | null>(null);
  const t = q.data;

  function setStatus(status: "accepted" | "discarded" | "proposed") {
    review.mutate(
      { id: tid, status },
      { onSuccess: () => toast.success(status === "accepted" ? "Accepted. It runs with the generated tests." : status === "discarded" ? "Discarded. It no longer runs." : "Back to proposed."), onError: (err) => toast.error(errorMessage(err)) },
    );
  }

  const back = (
    <Link href={`/projects/${pid}/tests`} className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-3.5" /> Tests
    </Link>
  );

  if (q.isPending) {
    return (
      <>
        <PageHeader eyebrow={back} title={<Skeleton className="h-7 w-72" />} />
        <Skeleton className="h-96 rounded-[14px]" />
      </>
    );
  }
  if (q.isError || !t) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <>
        <PageHeader eyebrow={back} title="Test" />
        <Surface>
          {missing ? (
            <EmptyState icon={FlaskConicalIcon} title="This test does not exist" description="It may belong to another project. Pick one from the list of tests." />
          ) : (
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          )}
        </Surface>
      </>
    );
  }

  const unit = readUnit(t.unit);
  const assertionLines = new Set(t.assertions.map((a) => a.line));
  return (
    <>
      <PageHeader
        eyebrow={back}
        title={<span className="font-mono text-[19px] break-all sm:text-[22px]">{t.name}</span>}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <TestKindChip kind={t.kind} />
            <TestStatusChip status={t.status} />
            {t.last_outcome && <OutcomeChip outcome={t.last_outcome} />}
            <span>
              {languageLabel(t.language)}, {frameworkLabel(t.framework)}, written {formatRelative(t.created_at)}
            </span>
          </span>
        }
        actions={
          <>
            {canReview && t.status !== "discarded" && (
              <Button variant="outline" disabled={review.isPending} onClick={() => setStatus("discarded")}>
                <BanIcon />
                Discard
              </Button>
            )}
            {canReview && (
              <Button
                variant="outline"
                disabled={regen.isPending}
                onClick={() => regen.mutate(tid, { onSuccess: (g) => setGenerationId(g.id), onError: (err) => toast.error(errorMessage(err)) })}
              >
                <RefreshCwIcon />
                Regenerate
              </Button>
            )}
            {canReview && t.status !== "accepted" && (
              <Button disabled={review.isPending} onClick={() => setStatus("accepted")}>
                <CheckIcon />
                Accept
              </Button>
            )}
            {canRun && t.status === "accepted" && (
              <Button onClick={() => setRunning(true)}>
                <PlayIcon />
                Run this test
              </Button>
            )}
          </>
        }
      />
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          <Surface>
            <SurfaceHeader title="What it checks" />
            <p className="px-5 pb-5 text-[13.5px] leading-relaxed">{t.description}</p>
          </Surface>
          <Surface>
            <SurfaceHeader title="Code" description={t.file_path} />
            <div className="px-5 pb-5">
              <CodeView code={t.code} language={t.language} label={t.file_path.split("/").pop()} marks={(n) => (assertionLines.has(n) ? "focus" : null)} />
            </div>
          </Surface>
        </div>
        <div className="min-w-0 space-y-4">
          <Assertions t={t} />
          {unit ? (
            <Surface>
              <SurfaceHeader
                title="The code it tests"
                description={`${unitKindLabel(unit.kind)} in ${unit.file}, lines ${unit.start_line} to ${unit.end_line}`}
              />
              <div className="space-y-3 px-5 pb-5">
                <p className="rounded-lg bg-muted px-3 py-2 font-mono text-[12px] [overflow-wrap:anywhere]">{unit.signature || unit.qualname}</p>
                {unit.source && <CodeView code={unit.source} language={t.language} startLine={unit.start_line} label={unit.qualname} maxHeight="22rem" />}
              </div>
            </Surface>
          ) : t.operation ? (
            <Surface>
              <SurfaceHeader title="The operation it tests" />
              <p className="px-5 pb-5 font-mono text-[13px]">{t.operation}</p>
            </Surface>
          ) : null}
          {t.last_run_id && (
            <Surface>
              <SurfaceHeader title="Last run" />
              <div className="flex items-center justify-between gap-3 px-5 pb-5">
                <OutcomeChip outcome={t.last_outcome} />
                <Link href={`/projects/${pid}/runs/${t.last_run_id}`} className="text-[12.5px] font-medium text-primary hover:underline">
                  Open the run
                </Link>
              </div>
            </Surface>
          )}
        </div>
      </div>
      {canRun && <StartRunDialog pid={pid} open={running} onOpenChange={setRunning} testIds={[t.id]} />}
      <Dialog open={!!generationId} onOpenChange={(o) => !o && setGenerationId(null)}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Regenerating this test</DialogTitle>
            <DialogDescription>A new version is written for the same code and proposed for review. This one stays as it is.</DialogDescription>
          </DialogHeader>
          {generationId && <GenerationResult pid={pid} generationId={generationId} onClose={() => setGenerationId(null)} />}
        </DialogContent>
      </Dialog>
    </>
  );
}

function Assertions({ t }: { t: TestDetail }) {
  return (
    <Surface>
      <SurfaceHeader
        title={
          <span className="inline-flex items-center gap-1.5">
            Assertions found <Hint term="assertion" />
          </span>
        }
        description={`${plural(t.assertions.length, "assertion")} that can fail. A test without one is refused.`}
      />
      <ul className="space-y-1.5 px-5 pb-5" data-qa="assertions">
        {t.assertions.map((a, i) => (
          <li key={`${a.line}-${i}`} className="rounded-lg bg-muted px-3 py-2">
            <div className="flex items-center gap-1.5 text-[11.5px] text-subtle">
              <TargetIcon className="size-3" aria-hidden />
              <span className="font-mono">{a.test}</span>, line {a.line}
            </div>
            <code className="mt-0.5 block font-mono text-[12.5px] whitespace-pre-wrap [overflow-wrap:anywhere]">{a.text}</code>
          </li>
        ))}
      </ul>
    </Surface>
  );
}
