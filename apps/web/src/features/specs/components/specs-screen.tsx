"use client";

import { ArrowLeftIcon, ArrowRightIcon, CheckCircle2Icon, CircleDashedIcon, FlaskConicalIcon, WaypointsIcon } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { RoleNote } from "@/components/role-note";
import { Segmented } from "@/components/segmented";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentProject } from "@/features/projects/api";
import { useTests } from "@/features/tests/api";
import { GenerateDialog } from "@/features/tests/components/generate-dialog";
import { ApiError, errorMessage } from "@/lib/api/errors";
import type { GeneratedTest, Operation } from "@/lib/api/types";
import { formatRelative, plural } from "@/lib/format";

import { useImportSpec, useSpec, useSpecs as useSpecsList } from "../api";

/** Operation keys ("GET /health") that a kept (not discarded) API test covers. */
export function coveredOperations(tests: Pick<GeneratedTest, "operation" | "status" | "kind">[]): Set<string> {
  return new Set(tests.filter((t) => t.kind === "api" && t.status !== "discarded" && t.operation).map((t) => t.operation as string));
}

const METHOD_TONE: Record<string, "success" | "info" | "warning" | "danger" | "neutral"> = { GET: "info", POST: "success", PUT: "warning", PATCH: "warning", DELETE: "danger" };

export function SpecsScreen() {
  const { pid, project, canImport } = useCurrentProject();
  const q = useSpecsList(pid);
  const [importing, setImporting] = React.useState(false);
  const list = q.data ?? [];
  return (
    <>
      <PageHeader
        title="API specs"
        description="Import an OpenAPI document and TestForge writes API tests that call every documented operation and check its status code and response shape."
        actions={
          canImport && list.length > 0 ? (
            <Button onClick={() => setImporting(true)}>
              <WaypointsIcon />
              Import an OpenAPI document
            </Button>
          ) : undefined
        }
      />
      {!canImport && project && <RoleNote className="mb-4">You can read imported documents and which operations are tested. Editors and admins import them.</RoleNote>}
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={3} cols={3} />
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} title="API specs could not be loaded" onRetry={() => void q.refetch()} />
        ) : !list.length ? (
          <EmptyState
            icon={WaypointsIcon}
            title="No OpenAPI document yet"
            description="Paste or upload your API's OpenAPI document (JSON or YAML). Every operation gets at least one test: status code and, where documented, the response schema."
            action={
              canImport ? (
                <Button onClick={() => setImporting(true)}>
                  <WaypointsIcon />
                  Import an OpenAPI document
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="space-y-0.5 p-3" data-qa="specs">
            {list.map((s) => (
              <li key={s.id}>
                <Link href={`/projects/${pid}/specs/${s.id}`} className="flex items-center gap-3 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
                    <WaypointsIcon className="size-4" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13.5px] font-medium">
                      {s.title} <span className="text-subtle">{s.version}</span>
                    </span>
                    <span className="block truncate text-[12px] text-subtle">
                      {plural(s.operation_count, "operation")}, imported {formatRelative(s.created_at)}
                    </span>
                  </span>
                  <ArrowRightIcon className="size-3.5 shrink-0 text-faint" />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Surface>
      {canImport && <ImportSpecDialog pid={pid} open={importing} onOpenChange={setImporting} />}
    </>
  );
}

function ImportSpecDialog({ pid, open, onOpenChange }: { pid: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const imp = useImportSpec(pid);
  const router = useRouter();
  const [mode, setMode] = React.useState<"paste" | "file">("paste");
  const [text, setText] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (open) {
      setMode("paste");
      setText("");
      setError(null);
    }
  }, [open]);

  async function onFile(file: File | undefined) {
    if (!file) return;
    setText(await file.text());
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return setError(mode === "paste" ? "Paste the OpenAPI document (JSON or YAML)." : "Choose the OpenAPI file.");
    setError(null);
    imp.mutate(text, {
      onSuccess: (s) => {
        onOpenChange(false);
        router.push(`/projects/${pid}/specs/${s.id}`);
      },
      onError: (err) => setError(errorMessage(err)),
    });
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !imp.isPending && onOpenChange(o)}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import an OpenAPI document</DialogTitle>
          <DialogDescription>OpenAPI 3, as JSON or YAML. Your FastAPI app serves its own at /openapi.json.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="space-y-4">
            <Segmented
              ariaLabel="How to provide the document"
              value={mode}
              onChange={setMode}
              options={[
                { value: "paste", label: "Paste" },
                { value: "file", label: "Upload a file" },
              ]}
            />
            {mode === "paste" ? (
              <Field label="Document" htmlFor="spec-text">
                <Textarea id="spec-text" rows={12} className="font-mono text-[12px]" placeholder='{"openapi": "3.1.0", "paths": {...}}' value={text} onChange={(e) => setText(e.target.value)} />
              </Field>
            ) : (
              <Field label="File" htmlFor="spec-file" hint={text ? `${plural(text.split("\n").length, "line")} read.` : "openapi.json or openapi.yaml"}>
                <Input id="spec-file" type="file" accept=".json,.yaml,.yml,application/json" className="pt-1.5" onChange={(e) => void onFile(e.target.files?.[0])} />
              </Field>
            )}
            {error && <FieldError>{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={imp.isPending}>
              {imp.isPending ? "Importing..." : "Import document"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function SpecDetailScreen() {
  const { pid, canGenerate, canAdmin } = useCurrentProject();
  const { sid } = useParams<{ sid: string }>();
  const q = useSpec(pid, sid);
  const tests = useTests(pid, { kind: "api" });
  const [generating, setGenerating] = React.useState(false);
  const s = q.data;
  const back = (
    <Link href={`/projects/${pid}/specs`} className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-3.5" /> API specs
    </Link>
  );
  if (q.isPending) {
    return (
      <>
        <PageHeader eyebrow={back} title={<Skeleton className="h-7 w-64" />} />
        <Skeleton className="h-80 rounded-[14px]" />
      </>
    );
  }
  if (q.isError || !s) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <>
        <PageHeader eyebrow={back} title="API spec" />
        <Surface>
          {missing ? <EmptyState icon={WaypointsIcon} title="This document is not here" description="Open one from the list, or import it." /> : <ErrorState error={q.error} onRetry={() => void q.refetch()} />}
        </Surface>
      </>
    );
  }
  const covered = coveredOperations(tests.data ?? []);
  const done = s.operations.filter((o) => covered.has(o.key)).length;
  return (
    <>
      <PageHeader
        eyebrow={back}
        title={`${s.title} ${s.version}`}
        description={`${plural(s.operation_count, "operation")}, ${done} covered by an API test. Imported ${formatRelative(s.created_at)}.`}
        actions={
          canGenerate ? (
            <Button onClick={() => setGenerating(true)}>
              <FlaskConicalIcon />
              Generate API tests
            </Button>
          ) : undefined
        }
      />
      <Surface>
        <SurfaceHeader
          title={
            <span className="inline-flex items-center gap-1.5">
              Operations <Hint term="apiTests" />
            </span>
          }
          description="Covered means a kept API test calls it."
        />
        <ul className="divide-y divide-hairline px-5 pb-3" data-qa="operations">
          {s.operations.map((o) => (
            <OperationRow key={o.key} o={o} covered={covered.has(o.key)} pid={pid} />
          ))}
        </ul>
      </Surface>
      {canGenerate && (
        <GenerateDialog pid={pid} open={generating} onOpenChange={setGenerating} scope={{ specId: s.id, label: `API tests for every operation of ${s.title}.` }} canAdmin={canAdmin} />
      )}
    </>
  );
}

function OperationRow({ o, covered, pid }: { o: Operation; covered: boolean; pid: string }) {
  const codes = Object.keys(o.responses ?? {}).join(", ");
  return (
    <li className="flex flex-wrap items-center gap-3 py-2.5" data-qa="operation">
      <Chip tone={METHOD_TONE[o.method.toUpperCase()] ?? "neutral"} className="w-16 justify-center font-mono">
        {o.method.toUpperCase()}
      </Chip>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-mono text-[13px] font-medium">{o.path}</span>
        <span className="block truncate text-[11.5px] text-subtle">
          {o.summary || o.operation_id}
          {codes ? `, responds ${codes}` : ""}
        </span>
      </span>
      {covered ? (
        <Link href={`/projects/${pid}/tests?kind=api`}>
          <Chip tone="success">
            <CheckCircle2Icon aria-hidden />
            Covered
          </Chip>
        </Link>
      ) : (
        <Chip tone="neutral">
          <CircleDashedIcon aria-hidden />
          Not tested
        </Chip>
      )}
    </li>
  );
}
