"use client";

import { ArrowLeftIcon, ArrowRightIcon, FlaskConicalIcon, GitPullRequestIcon, Loader2Icon } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { RoleNote } from "@/components/role-note";
import { ImportStatusChip } from "@/components/status-chips";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentProject } from "@/features/projects/api";
import { UnitList } from "@/features/source/components/units-panel";
import { GenerateDialog } from "@/features/tests/components/generate-dialog";
import { ApiError, errorMessage } from "@/lib/api/errors";
import type { Pull } from "@/lib/api/types";
import { formatRanges, readChangedFiles } from "@/lib/code";
import { formatRelative, plural, shortSha } from "@/lib/format";
import { inFlight } from "@/lib/status";

import { useImportPull, usePull, usePulls } from "../api";

/** "+11 -2" for a pull request's size. */
export function diffStat(p: Pick<Pull, "changed_files">): { files: number; additions: number; deletions: number } {
  const files = readChangedFiles(p.changed_files);
  return { files: files.length, additions: files.reduce((a, f) => a + f.additions, 0), deletions: files.reduce((a, f) => a + f.deletions, 0) };
}

export function PullsScreen() {
  const { pid, project, canImport } = useCurrentProject();
  const q = usePulls(pid);
  const [importing, setImporting] = React.useState(false);
  const list = q.data ?? [];
  return (
    <>
      <PageHeader
        title="Pull requests"
        description="Import a pull request to see what it changes and generate tests only for the functions and routes it touches."
        actions={
          canImport && list.length > 0 ? (
            <Button onClick={() => setImporting(true)}>
              <GitPullRequestIcon />
              Import a pull request
            </Button>
          ) : undefined
        }
      />
      {!canImport && project && <RoleNote className="mb-4">You can read imported pull requests. Editors and admins import them and generate tests.</RoleNote>}
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={4} cols={3} />
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} title="Pull requests could not be loaded" onRetry={() => void q.refetch()} />
        ) : !list.length ? (
          <EmptyState
            icon={GitPullRequestIcon}
            title="No pull requests imported"
            description={
              project?.github_repo
                ? `Import one from ${project.github_repo} by its number. TestForge diffs it against its base and keeps only the code it changes.`
                : "Connect a GitHub repository first (import it as code, or set it in Settings, GitHub), then import a pull request by its number."
            }
            action={
              canImport ? (
                <Button onClick={() => setImporting(true)}>
                  <GitPullRequestIcon />
                  Import a pull request
                </Button>
              ) : undefined
            }
          />
        ) : (
          <ul className="space-y-0.5 p-3" data-qa="pulls">
            {list.map((p) => {
              const s = diffStat(p);
              return (
                <li key={p.id}>
                  <Link
                    href={`/projects/${pid}/pulls/${p.id}`}
                    className="flex items-center gap-3 rounded-xl px-2.5 py-2.5 transition-colors hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
                  >
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary">
                      <GitPullRequestIcon className="size-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-[13.5px] font-medium">
                          #{p.number} {p.title}
                        </span>
                        <ImportStatusChip status={p.status} />
                      </span>
                      <span className="mt-0.5 block truncate text-[12px] text-subtle">
                        {p.repo}, {p.head_ref} into {p.base_ref}, by {p.author}, {plural(s.files, "file")} <span className="text-savings">+{s.additions}</span>{" "}
                        <span className="text-danger">-{s.deletions}</span>, {plural(p.scoped_unit_ids.length, "unit")} in scope, {formatRelative(p.created_at)}
                      </span>
                    </span>
                    <ArrowRightIcon className="size-3.5 shrink-0 text-faint" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Surface>
      {canImport && <ImportPullDialog pid={pid} open={importing} onOpenChange={setImporting} defaultRepo={project?.github_repo ?? ""} />}
    </>
  );
}

function ImportPullDialog({ pid, open, onOpenChange, defaultRepo }: { pid: string; open: boolean; onOpenChange: (o: boolean) => void; defaultRepo: string }) {
  const imp = useImportPull(pid);
  const router = useRouter();
  const [repo, setRepo] = React.useState(defaultRepo);
  const [number, setNumber] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (open) {
      setRepo(defaultRepo);
      setNumber("");
      setError(null);
    }
  }, [open, defaultRepo]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const n = Number(number);
    if (!Number.isInteger(n) || n < 1) return setError("Enter the pull request number, like 12.");
    if (!repo.trim()) return setError("Name the repository as owner/name.");
    setError(null);
    imp.mutate(
      { number: n, repo: repo.trim() },
      {
        onSuccess: (p) => {
          onOpenChange(false);
          router.push(`/projects/${pid}/pulls/${p.id}`);
        },
        onError: (err) => setError(errorMessage(err)),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !imp.isPending && onOpenChange(o)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Import a pull request</DialogTitle>
          <DialogDescription>Its head commit is analyzed and compared with its base, so generation covers only what it changes.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
          <DialogBody className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <Field label="Repository" htmlFor="pr-repo">
              <Input id="pr-repo" placeholder="euron-demo/python-shop" value={repo} onChange={(e) => setRepo(e.target.value)} />
            </Field>
            <Field label="Number" htmlFor="pr-number">
              <Input id="pr-number" inputMode="numeric" autoFocus placeholder="12" value={number} onChange={(e) => setNumber(e.target.value)} />
            </Field>
            {error && <FieldError className="sm:col-span-2">{error}</FieldError>}
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={imp.isPending}>
              {imp.isPending ? "Importing..." : "Import pull request"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function PullDetailScreen() {
  const { pid, canGenerate, canAdmin } = useCurrentProject();
  const { prid } = useParams<{ prid: string }>();
  const q = usePull(pid, prid);
  const [generating, setGenerating] = React.useState(false);
  const p = q.data;
  const back = (
    <Link href={`/projects/${pid}/pulls`} className="inline-flex items-center gap-1 text-[12.5px] font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeftIcon className="size-3.5" /> Pull requests
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
  if (q.isError || !p) {
    const missing = q.error instanceof ApiError && q.error.status === 404;
    return (
      <>
        <PageHeader eyebrow={back} title="Pull request" />
        <Surface>
          {missing ? (
            <EmptyState icon={GitPullRequestIcon} title="This pull request is not imported here" description="Open one from the list, or import it by its number." />
          ) : (
            <ErrorState error={q.error} onRetry={() => void q.refetch()} />
          )}
        </Surface>
      </>
    );
  }
  const files = readChangedFiles(p.changed_files);
  const s = diffStat(p);
  const units = p.scoped_units ?? [];
  return (
    <>
      <PageHeader
        eyebrow={back}
        title={
          <span>
            #{p.number} {p.title}
          </span>
        }
        description={`${p.repo}: ${p.head_ref} (${shortSha(p.head_sha)}) into ${p.base_ref} (${shortSha(p.base_sha)}), by ${p.author}, imported ${formatRelative(p.created_at)}.`}
        actions={
          canGenerate && p.status === "ready" && units.length > 0 ? (
            <Button onClick={() => setGenerating(true)}>
              <FlaskConicalIcon />
              Generate tests for this change
            </Button>
          ) : (
            <ImportStatusChip status={p.status} />
          )
        }
      />
      {inFlight(p.status) && (
        <div className="mb-4 flex items-center gap-3 rounded-[14px] bg-primary-soft px-5 py-4 text-[13px]" aria-live="polite">
          <Loader2Icon className="size-4 animate-spin text-primary" />
          Fetching the diff and analyzing the head commit.
        </div>
      )}
      {p.status === "failed" && <FieldError className="mb-4">{p.error ?? "The pull request could not be imported."}</FieldError>}
      <div className="grid min-w-0 gap-4 xl:grid-cols-2">
        <Surface>
          <SurfaceHeader
            title="Changed files"
            description={
              <>
                {plural(s.files, "file")}, <span className="text-savings">+{s.additions}</span> <span className="text-danger">-{s.deletions}</span>
              </>
            }
          />
          <ul className="divide-y divide-hairline px-5 pb-3" data-qa="changed-files">
            {files.map((f) => (
              <li key={f.path} className="py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="min-w-0 flex-1 truncate font-mono text-[12.5px] font-medium">{f.path}</span>
                  <Chip tone={f.status === "added" ? "success" : f.status === "removed" ? "danger" : "neutral"}>{f.status}</Chip>
                  <span className="tabular text-[12px]">
                    <span className="text-savings">+{f.additions}</span> <span className="text-danger">-{f.deletions}</span>
                  </span>
                </div>
                <div className="mt-0.5 text-[11.5px] text-subtle">Changed lines: {formatRanges(f.changed)}</div>
              </li>
            ))}
            {!files.length && <li className="py-4 text-[13px] text-muted-foreground">No changed files reported yet.</li>}
          </ul>
        </Surface>
        <Surface>
          <SurfaceHeader
            title={
              <span className="inline-flex items-center gap-1.5">
                In scope for testing <Hint term="pullScope" />
              </span>
            }
            description={`${plural(units.length, "unit")} whose lines this change touches. Generation covers only these.`}
          />
          <div className="px-3 pb-3">
            {units.length && p.import_id ? (
              <UnitList pid={pid} iid={p.import_id} units={units} canGenerate={canGenerate} canAdmin={canAdmin} />
            ) : (
              <EmptyState
                compact
                icon={FlaskConicalIcon}
                title={p.status === "ready" ? "Nothing to test in this change" : "Not analyzed yet"}
                description={p.status === "ready" ? "The change touches no function, class or route (only docs, config or tests)." : "The units appear when the head commit is analyzed."}
              />
            )}
          </div>
        </Surface>
      </div>
      {canGenerate && (
        <GenerateDialog
          pid={pid}
          open={generating}
          onOpenChange={setGenerating}
          scope={{ pullId: p.id, label: `Tests only for the ${plural(units.length, "unit")} pull request #${p.number} changes.` }}
          canAdmin={canAdmin}
        />
      )}
    </>
  );
}
