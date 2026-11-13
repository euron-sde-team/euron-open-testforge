"use client";

import { CheckIcon, FileArchiveIcon, GithubIcon, Loader2Icon, XIcon } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Segmented } from "@/components/segmented";
import { Button } from "@/components/ui/button";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Field, FieldError } from "@/components/ui/label";
import { errorMessage } from "@/lib/api/errors";
import type { Import } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatBytes, formatDuration, formatNumber, plural } from "@/lib/format";
import { frameworkLabel, importStep, languageLabel } from "@/lib/status";

import { useImport, useImportGithub, useImportZip, useRefreshAfterImport } from "../api";

type Source = "github" | "zip";

/**
 * Bring code into a project: a GitHub repository at a branch, tag or commit, or a ZIP.
 * After it is sent the dialog follows the analysis step by step and shows what was found.
 */
export function ImportDialog({
  pid,
  open,
  onOpenChange,
  defaultRepo,
}: {
  pid: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultRepo?: string | null;
}) {
  const github = useImportGithub(pid);
  const zip = useImportZip(pid);
  const [source, setSource] = React.useState<Source>("github");
  const [repo, setRepo] = React.useState("");
  const [ref, setRef] = React.useState("");
  const [file, setFile] = React.useState<File | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [importId, setImportId] = React.useState<string | null>(null);
  const pending = github.isPending || zip.isPending;

  // Reset only when the dialog opens: the project (and its repository) refetches when an
  // import finishes, and that must not wipe the progress being shown.
  const wasOpen = React.useRef(false);
  React.useEffect(() => {
    if (open && !wasOpen.current) {
      setSource("github");
      setRepo(defaultRepo ?? "");
      setRef("");
      setFile(null);
      setError(null);
      setImportId(null);
    }
    wasOpen.current = open;
  }, [open, defaultRepo]);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const done = { onSuccess: (imp: Import) => setImportId(imp.id), onError: (err: unknown) => setError(errorMessage(err)) };
    if (source === "github") {
      if (!repo.trim()) return setError("Name the repository as owner/name, for example euron-demo/python-shop.");
      github.mutate({ repo: repo.trim(), ref: ref.trim() || null }, done);
    } else {
      if (!file) return setError("Choose a .zip of the project.");
      zip.mutate(file, done);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{importId ? "Importing your code" : "Import code"}</DialogTitle>
          <DialogDescription>
            Python and JavaScript or TypeScript. The code is read and analyzed, never run here; it only runs inside the sandbox, when you start a run.
          </DialogDescription>
        </DialogHeader>
        {importId ? (
          <ImportProgress pid={pid} importId={importId} onClose={() => onOpenChange(false)} />
        ) : (
          <form onSubmit={submit} className="flex min-h-0 flex-col" noValidate>
            <DialogBody className="space-y-4">
              <Segmented<Source>
                ariaLabel="Where the code comes from"
                value={source}
                onChange={setSource}
                options={[
                  {
                    value: "github",
                    label: (
                      <span className="inline-flex items-center gap-1.5">
                        <GithubIcon className="size-3.5" /> GitHub
                      </span>
                    ),
                  },
                  {
                    value: "zip",
                    label: (
                      <span className="inline-flex items-center gap-1.5">
                        <FileArchiveIcon className="size-3.5" /> ZIP upload
                      </span>
                    ),
                  },
                ]}
              />
              {source === "github" ? (
                <div className="grid gap-4 sm:grid-cols-[1fr_10rem]">
                  <Field label="Repository" htmlFor="im-repo" hint="owner/name or the repository URL. A private one needs a token in Settings, GitHub.">
                    <Input id="im-repo" autoFocus placeholder="euron-demo/python-shop" value={repo} onChange={(e) => setRepo(e.target.value)} />
                  </Field>
                  <Field label="Branch, tag or commit" htmlFor="im-ref" hint="Empty uses the default branch.">
                    <Input id="im-ref" placeholder="main" value={ref} onChange={(e) => setRef(e.target.value)} />
                  </Field>
                </div>
              ) : (
                <Field label="Project archive" htmlFor="im-zip" hint="A .zip of the project folder. Links and paths outside the project are refused.">
                  <Input id="im-zip" type="file" accept=".zip,application/zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="pt-1.5" />
                </Field>
              )}
              {error && <FieldError role="alert">{error}</FieldError>}
            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={pending}>
                {pending ? "Sending..." : source === "github" ? "Import repository" : "Upload and analyze"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

const STEPS = ["Code received", "Analyzing the source", "Ready to generate tests"];

/** Follows one import until it is analyzed, then shows what was found and where to go next. */
export function ImportProgress({ pid, importId, onClose }: { pid: string; importId: string; onClose: () => void }) {
  const q = useImport(pid, importId);
  const refresh = useRefreshAfterImport(pid);
  const imp = q.data;
  const step = imp ? importStep(imp.status) : 0;
  const failed = imp?.status === "failed";
  const ready = imp?.status === "ready";
  React.useEffect(() => {
    if (ready || failed) refresh();
    // refresh once when the import settles
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, failed]);

  const summary = (imp?.summary ?? {}) as { units?: number; untested?: number; source_files?: number; test_file_count?: number };
  return (
    <>
      <DialogBody className="space-y-5" aria-live="polite">
        <ol className="space-y-2.5" data-qa="import-progress">
          {STEPS.map((label, i) => {
            const done = step > i || (ready && i === 2);
            const active = !done && !failed && step === i;
            const bad = failed && i === Math.max(1, step) ;
            return (
              <li key={label} className="flex items-center gap-3 text-[13.5px]">
                <span
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-subtle",
                    done && "bg-primary text-primary-foreground",
                    active && "bg-primary-soft text-primary",
                    bad && "bg-danger-soft text-danger",
                  )}
                >
                  {done ? <CheckIcon className="size-3.5" /> : bad ? <XIcon className="size-3.5" /> : active ? <Loader2Icon className="size-3.5 animate-spin" /> : i + 1}
                </span>
                <span className={cn(done || active ? "font-medium text-foreground" : "text-muted-foreground")}>{bad ? "The import failed" : label}</span>
              </li>
            );
          })}
        </ol>
        {!ready && !failed && (
          <div className="h-1 overflow-hidden rounded-full bg-muted" aria-hidden>
            <div className="h-full w-1/3 animate-[tf-indeterminate_1.2s_ease-in-out_infinite] rounded-full bg-primary" />
          </div>
        )}
        {failed && <FieldError role="alert">{imp?.error ?? "The code could not be analyzed."} Fix the source or the repository name, then import again.</FieldError>}
        {q.isError && <FieldError role="alert">{errorMessage(q.error)}</FieldError>}
        {ready && imp && (
          <div className="rounded-xl bg-muted/70 p-4" data-qa="import-result">
            <div className="text-[13.5px] font-semibold">{imp.label}</div>
            <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-2.5 text-[12.5px] sm:grid-cols-3">
              <Fact label="Languages" value={imp.languages.map(languageLabel).join(", ") || "None found"} />
              <Fact label="Frameworks" value={[...imp.frameworks, ...imp.test_frameworks].map(frameworkLabel).join(", ") || "None found"} />
              <Fact label="Files" value={`${formatNumber(imp.file_count)}, ${formatBytes(imp.size_bytes)}`} />
              <Fact label="Code units" value={plural(summary.units ?? 0, "unit")} />
              <Fact label="Not tested" value={plural(summary.untested ?? 0, "unit")} />
              <Fact label="Analysis" value={imp.analysis_ms != null ? formatDuration(imp.analysis_ms) : "n/a"} />
            </dl>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        {ready ? (
          <>
            <Button variant="ghost" nativeButton={false} render={<Link href={`/projects/${pid}/source`} onClick={onClose} />}>
              Explore the source
            </Button>
            <Button nativeButton={false} render={<Link href={`/projects/${pid}/source?tab=units&untested=1`} onClick={onClose} />}>
              Generate tests for untested code
            </Button>
          </>
        ) : (
          <Button variant="ghost" onClick={onClose}>
            {failed ? "Close" : "Keep working, it continues in the background"}
          </Button>
        )}
      </DialogFooter>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] font-medium text-subtle">{label}</dt>
      <dd className="truncate font-medium text-foreground">{value}</dd>
    </div>
  );
}
