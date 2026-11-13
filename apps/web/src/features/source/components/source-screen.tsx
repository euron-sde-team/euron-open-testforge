"use client";

import { ChevronDownIcon, ChevronRightIcon, FileCode2Icon, FileIcon, FolderIcon, ListTreeIcon, UploadIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { CodeLegend, CodeView, type LineMark } from "@/components/code-view";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { PageHeader } from "@/components/page-header";
import { CoverageBar } from "@/components/status-chips";
import { Surface, SurfaceHeader } from "@/components/surface";
import { Skeleton } from "@/components/ui/skeleton";
import { SimpleSelect } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ImportDialog } from "@/features/imports/components/import-dialog";
import { useImports } from "@/features/imports/api";
import { useCurrentProject } from "@/features/projects/api";
import { buildTree, type TreeNode } from "@/lib/code";
import { cn } from "@/lib/cn";
import { formatBytes, formatPercent, formatRelative, plural, shortSha } from "@/lib/format";
import { useTabParam } from "@/lib/use-tab-param";

import { useFile, useFiles } from "../api";

import { UnitsPanel, UnitList } from "./units-panel";

const TABS = ["files", "units"] as const;

export function SourceScreen() {
  const { pid, project, canImport, canGenerate, canAdmin } = useCurrentProject();
  const imports = useImports(pid);
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [tab, setTab] = useTabParam("files", TABS);
  const [importing, setImporting] = React.useState(false);
  const ready = (imports.data ?? []).filter((i) => i.status === "ready");
  const iid = ready.find((i) => i.id === params.get("import"))?.id ?? project?.current_import_id ?? ready[0]?.id ?? null;
  const current = imports.data?.find((i) => i.id === iid);

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  return (
    <>
      <PageHeader
        title="Source"
        description="The imported code as TestForge analyzed it: every file with its covered and missing lines, and every function, class, method and route with its coverage."
        actions={
          ready.length > 1 ? (
            <SimpleSelect
              aria-label="Import"
              className="w-full sm:w-80"
              value={iid ?? ""}
              onValueChange={(v) => setParam("import", v === project?.current_import_id ? null : v)}
              options={ready.map((i) => ({ value: i.id, label: `${i.kind === "pull_request" ? "Pull request: " : ""}${i.label.split("@")[0]}${i.commit_sha ? ` @ ${shortSha(i.commit_sha)}` : ""}` }))}
            />
          ) : undefined
        }
      />
      {imports.isPending || !project ? (
        <Skeleton className="h-96 rounded-[14px]" />
      ) : imports.isError ? (
        <div className="surface">
          <ErrorState error={imports.error} title="The imports could not be loaded" onRetry={() => void imports.refetch()} />
        </div>
      ) : !iid ? (
        <Surface>
          <EmptyState
            icon={FileCode2Icon}
            title="No code to explore yet"
            description="Import a GitHub repository or a ZIP. Its files, units and coverage gaps appear here once it is analyzed."
            action={
              canImport ? (
                <Button onClick={() => setImporting(true)}>
                  <UploadIcon />
                  Import code
                </Button>
              ) : undefined
            }
          />
        </Surface>
      ) : (
        <>
          {current && (
            <p className="mb-4 text-[12.5px] text-muted-foreground">
              {current.label.split("@")[0]}
              {current.ref ? `, ${current.ref}` : ""}
              {current.commit_sha ? `, commit ${shortSha(current.commit_sha)}` : ""}, {plural(current.file_count, "file")}, analyzed {formatRelative(current.analyzed_at)}
            </p>
          )}
          <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
            <TabsList>
              <TabsTrigger value="files">
                <FileCode2Icon />
                Files
              </TabsTrigger>
              <TabsTrigger value="units">
                <ListTreeIcon />
                Units
              </TabsTrigger>
            </TabsList>
            <TabsContent value="files">
              <FilesPanel pid={pid} iid={iid} path={params.get("file")} onPath={(p) => setParam("file", p)} canGenerate={canGenerate} canAdmin={canAdmin} />
            </TabsContent>
            <TabsContent value="units">
              <UnitsPanel pid={pid} iid={iid} canGenerate={canGenerate} canAdmin={canAdmin} />
            </TabsContent>
          </Tabs>
        </>
      )}
      {canImport && <ImportDialog pid={pid} open={importing} onOpenChange={setImporting} defaultRepo={project?.github_repo} />}
    </>
  );
}

function FilesPanel({
  pid,
  iid,
  path,
  onPath,
  canGenerate,
  canAdmin,
}: {
  pid: string;
  iid: string;
  path: string | null;
  onPath: (p: string) => void;
  canGenerate: boolean;
  canAdmin: boolean;
}) {
  const files = useFiles(pid, iid);
  const list = React.useMemo(() => files.data ?? [], [files.data]);
  const firstCode = list.find((f) => f.language && !/(^|\/)tests?\//.test(f.path))?.path ?? list[0]?.path ?? null;
  const selected = list.some((f) => f.path === path) ? path : firstCode;
  const tree = React.useMemo(() => buildTree(list.map((f) => f.path)), [list]);

  if (files.isPending) return <Skeleton className="h-96 rounded-[14px]" />;
  if (files.isError) return <div className="surface"><ErrorState error={files.error} onRetry={() => void files.refetch()} /></div>;
  if (!list.length) {
    return (
      <Surface>
        <EmptyState icon={FileIcon} title="This import has no files" description="The archive was empty or held only files TestForge skips (binaries, dependencies). Import the project folder itself." />
      </Surface>
    );
  }
  return (
    <div className="grid min-w-0 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <Surface className="self-start p-2">
        <nav aria-label="Files" className="max-h-[32rem] overflow-y-auto lg:max-h-[70vh]">
          <Tree nodes={tree} selected={selected} onSelect={onPath} sizes={new Map(list.map((f) => [f.path, f.bytes]))} />
        </nav>
      </Surface>
      {selected && <FileView pid={pid} iid={iid} path={selected} canGenerate={canGenerate} canAdmin={canAdmin} />}
    </div>
  );
}

function Tree({ nodes, selected, onSelect, sizes, depth = 0 }: { nodes: TreeNode[]; selected: string | null; onSelect: (p: string) => void; sizes: Map<string, number>; depth?: number }) {
  return (
    <ul className="space-y-px">
      {nodes.map((n) => (
        <TreeItem key={n.path} node={n} selected={selected} onSelect={onSelect} sizes={sizes} depth={depth} />
      ))}
    </ul>
  );
}

function TreeItem({ node, selected, onSelect, sizes, depth }: { node: TreeNode; selected: string | null; onSelect: (p: string) => void; sizes: Map<string, number>; depth: number }) {
  const [open, setOpen] = React.useState(true);
  const pad = { paddingLeft: `${0.5 + depth * 0.85}rem` };
  if (node.dir) {
    return (
      <li>
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="flex h-7 w-full items-center gap-1.5 rounded-md pr-2 text-left text-[12.5px] font-medium text-muted-foreground hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
          style={pad}
        >
          {open ? <ChevronDownIcon className="size-3.5 shrink-0" /> : <ChevronRightIcon className="size-3.5 shrink-0" />}
          <FolderIcon className="size-3.5 shrink-0 text-subtle" />
          <span className="truncate">{node.name}</span>
        </button>
        {open && <Tree nodes={node.children} selected={selected} onSelect={onSelect} sizes={sizes} depth={depth + 1} />}
      </li>
    );
  }
  const active = node.path === selected;
  return (
    <li>
      <button
        type="button"
        aria-current={active ? "true" : undefined}
        onClick={() => onSelect(node.path)}
        className={cn(
          "flex h-7 w-full items-center gap-1.5 rounded-md pr-2 text-left text-[12.5px] text-foreground hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring",
          active && "bg-primary-soft font-medium text-primary hover:bg-primary-soft",
        )}
        style={{ paddingLeft: `${1.4 + depth * 0.85}rem` }}
        data-qa="tree-file"
      >
        <FileIcon className="size-3.5 shrink-0 opacity-60" />
        <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{node.name}</span>
        <span className="shrink-0 text-[10.5px] text-faint">{formatBytes(sizes.get(node.path) ?? 0)}</span>
      </button>
    </li>
  );
}

function FileView({ pid, iid, path, canGenerate, canAdmin }: { pid: string; iid: string; path: string; canGenerate: boolean; canAdmin: boolean }) {
  const q = useFile(pid, iid, path);
  const f = q.data;
  const covered = React.useMemo(() => new Set(f?.covered_lines ?? []), [f]);
  const missing = React.useMemo(() => new Set(f?.missing_lines ?? []), [f]);
  const measured = covered.size + missing.size;
  const percent = measured ? (covered.size / measured) * 100 : null;
  const marks = (n: number): LineMark | null => (missing.has(n) ? "missing" : covered.has(n) ? "covered" : null);

  return (
    <div className="min-w-0 space-y-4">
      <Surface>
        <SurfaceHeader
          title={<span className="font-mono text-[13px] break-all">{path}</span>}
          description={
            f
              ? measured
                ? `${formatPercent(percent)} of ${plural(measured, "statement line")} covered by the latest run`
                : "No coverage measured for this file yet. Run the tests to see covered and missing lines."
              : undefined
          }
          action={percent != null ? <CoverageBar percent={percent} className="w-28" /> : undefined}
        />
        <div className="space-y-3 px-5 pb-5">
          {q.isPending ? (
            <Skeleton className="h-80 w-full" />
          ) : q.isError ? (
            <ErrorState compact error={q.error} onRetry={() => void q.refetch()} />
          ) : f ? (
            <>
              {measured > 0 && (
                <CodeLegend
                  items={[
                    { mark: "covered", label: `${covered.size} covered` },
                    { mark: "missing", label: `${missing.size} not run by any test` },
                  ]}
                />
              )}
              <CodeView code={f.content} language={f.language} label={f.language ?? "text"} marks={marks} maxHeight="36rem" />
            </>
          ) : null}
        </div>
      </Surface>
      {f && f.units.length > 0 && (
        <Surface>
          <SurfaceHeader title="Units in this file" description="Functions, classes, methods and routes, with their coverage." />
          <div className="px-3 pb-3">
            <UnitList pid={pid} iid={iid} units={f.units} canGenerate={canGenerate} canAdmin={canAdmin} />
          </div>
        </Surface>
      )}
      {f && f.units.length === 0 && f.language && (
        <p className="px-1 text-[12.5px] text-muted-foreground">
          No functions, classes or routes in this file. <Link href="?tab=units" className="font-medium text-primary hover:underline">See every unit</Link>.
        </p>
      )}
    </div>
  );
}
