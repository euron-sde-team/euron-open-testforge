"use client";

import { BanIcon, CheckIcon, ChevronDownIcon, ChevronRightIcon, FlaskConicalIcon, XIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { PageHeader } from "@/components/page-header";
import { RoleNote } from "@/components/role-note";
import { Segmented } from "@/components/segmented";
import { GenerationStatusChip, OutcomeChip, TestKindChip, TestStatusChip } from "@/components/status-chips";
import { Surface, SurfaceHeader } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { SimpleSelect } from "@/components/ui/select";
import { useCurrentProject } from "@/features/projects/api";
import { errorMessage } from "@/lib/api/errors";
import type { Generation } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatRelative, plural, shortId } from "@/lib/format";
import { TEST_KIND_LABEL } from "@/lib/status";

import { useBulkReview, useGenerations, useTests } from "../api";

import { GenerateDialog, GenerationSummary } from "./generate-dialog";

type StatusFilter = "" | "proposed" | "accepted" | "discarded";

export function TestsScreen() {
  const { pid, project, canGenerate, canReview, canAdmin } = useCurrentProject();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const status = (params.get("status") ?? "") as StatusFilter;
  const kind = params.get("kind") ?? "";
  const generation = params.get("generation") ?? "";
  const q = useTests(pid, { status, kind, generation_id: generation });
  const gens = useGenerations(pid);
  const bulk = useBulkReview(pid);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [generating, setGenerating] = React.useState(false);
  const list = q.data ?? [];
  const noCode = project && !project.current_import_id;

  React.useEffect(() => setSelected(new Set()), [status, kind, generation]);

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  function review(next: "accepted" | "discarded") {
    const ids = [...selected];
    bulk.mutate(
      { ids, status: next },
      {
        onSuccess: (r) => {
          toast.success(`${plural(r.changed, "test")} ${next}.`);
          setSelected(new Set());
        },
        onError: (err) => toast.error(errorMessage(err)),
      },
    );
  }

  const allOn = list.length > 0 && list.every((t) => selected.has(t.id));

  return (
    <>
      <PageHeader
        title="Tests"
        description="Every test TestForge wrote, with what it checks. Proposed tests wait for review; only accepted tests run."
        actions={
          canGenerate && !noCode ? (
            <Button onClick={() => setGenerating(true)}>
              <FlaskConicalIcon />
              Generate tests
            </Button>
          ) : undefined
        }
      />
      {!canReview && project && <RoleNote className="mb-4">You can read every test and its assertions. Editors and admins generate, accept and run them.</RoleNote>}
      <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented<StatusFilter>
            ariaLabel="Status"
            value={status}
            onChange={(v) => setParam("status", v || null)}
            options={[
              { value: "", label: "All" },
              { value: "proposed", label: "Proposed" },
              { value: "accepted", label: "Accepted" },
              { value: "discarded", label: "Discarded" },
            ]}
            className="w-full sm:w-auto"
          />
          <SimpleSelect
            aria-label="Kind of test"
            className="w-40"
            value={kind}
            onValueChange={(v) => setParam("kind", v || null)}
            options={[{ value: "", label: "Every kind" }, ...Object.entries(TEST_KIND_LABEL).map(([value, label]) => ({ value, label }))]}
          />
          {generation && (
            <Chip tone="primary" className="h-7 gap-1.5 px-2.5">
              Generation {shortId(generation)}
              <button type="button" aria-label="Show tests from every generation" onClick={() => setParam("generation", null)} className="rounded-full hover:opacity-70">
                <XIcon />
              </button>
            </Chip>
          )}
        </div>
        {canReview && selected.size > 0 && (
          <div className="flex items-center gap-2" data-qa="bulk-actions">
            <span className="text-[12.5px] text-muted-foreground">{selected.size} selected</span>
            <Button size="sm" variant="outline" disabled={bulk.isPending} onClick={() => review("discarded")}>
              <BanIcon />
              Discard
            </Button>
            <Button size="sm" disabled={bulk.isPending} onClick={() => review("accepted")}>
              <CheckIcon />
              Accept
            </Button>
          </div>
        )}
      </div>
      {!generation && gens.data && gens.data.length > 0 && <Generations gens={gens.data} />}
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={8} cols={4} />
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} title="The tests could not be loaded" onRetry={() => void q.refetch()} />
        ) : !list.length ? (
          status || kind || generation ? (
            <EmptyState
              icon={FlaskConicalIcon}
              title="No tests match these filters"
              description="Clear the filters to see every test in this project."
              action={
                <Button variant="outline" size="sm" onClick={() => router.replace(pathname, { scroll: false })}>
                  Clear filters
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={FlaskConicalIcon}
              title="No tests generated yet"
              description={
                noCode
                  ? "Import the code first. TestForge then writes unit, edge case, negative and API tests grounded in it."
                  : "TestForge writes unit, edge case, negative and API tests grounded in the analyzed code. Each one checks real values; tests that could never fail are refused."
              }
              action={
                canGenerate ? (
                  noCode ? (
                    <Button nativeButton={false} render={<Link href={`/projects/${pid}?import=1`} />}>
                      Import code
                    </Button>
                  ) : (
                    <Button onClick={() => setGenerating(true)}>
                      <FlaskConicalIcon />
                      Generate tests
                    </Button>
                  )
                ) : undefined
              }
            />
          )
        ) : (
          <>
            {canReview && (
              <div className="flex items-center gap-3 px-5 pt-3 pb-1 text-[12.5px] text-muted-foreground">
                <Box on={allOn} label="Select every test shown" onToggle={() => setSelected(allOn ? new Set() : new Set(list.map((t) => t.id)))} />
                {plural(list.length, "test")}
              </div>
            )}
            <ul className="divide-y divide-hairline px-3 pb-2" data-qa="tests">
              {list.map((t) => (
                <li key={t.id} className="flex items-start gap-3 px-2 py-3" data-qa="test-row">
                  {canReview && (
                    <span className="pt-0.5">
                      <Box
                        on={selected.has(t.id)}
                        label={`Select ${t.name}`}
                        onToggle={() =>
                          setSelected((cur) => {
                            const next = new Set(cur);
                            if (next.has(t.id)) next.delete(t.id);
                            else next.add(t.id);
                            return next;
                          })
                        }
                      />
                    </span>
                  )}
                  <Link href={`/projects/${pid}/tests/${t.id}`} className="min-w-0 flex-1 rounded-lg focus-visible:outline-2 focus-visible:outline-ring">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[13px] font-medium break-all text-foreground hover:text-primary">{t.name}</span>
                      <TestKindChip kind={t.kind} />
                      <TestStatusChip status={t.status} />
                      {t.last_outcome && <OutcomeChip outcome={t.last_outcome} />}
                    </span>
                    <span className="mt-1 line-clamp-2 block text-[12.5px] leading-relaxed text-muted-foreground">{t.description}</span>
                    <span className="mt-1 block truncate text-[11.5px] text-subtle">
                      {plural(t.assertions.length, "assertion")}, {t.operation ?? t.file_path}, {formatRelative(t.created_at)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </Surface>
      {canGenerate && (
        <GenerateDialog
          pid={pid}
          open={generating}
          onOpenChange={setGenerating}
          scope={{ label: "Tests for the whole current import. To aim at specific code, pick units in Source or a pull request." }}
          canAdmin={canAdmin}
        />
      )}
    </>
  );
}

function Box({ on, label, onToggle }: { on: boolean; label: string; onToggle: () => void }) {
  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={on}
      aria-label={label}
      onClick={onToggle}
      className={cn("flex size-4 shrink-0 items-center justify-center rounded ring-1 ring-input focus-visible:outline-2 focus-visible:outline-ring", on && "bg-primary text-primary-foreground ring-primary")}
    >
      {on && <CheckIcon className="size-3" strokeWidth={3} />}
    </button>
  );
}

/** Each generation with how many tests it proposed and refused, and why. */
function Generations({ gens }: { gens: Generation[] }) {
  // The latest generation that refused tests starts open: what was refused, and why.
  const [open, setOpen] = React.useState<string | null>(() => gens.find((g) => g.rejected_count > 0)?.id ?? null);
  return (
    <Surface className="mb-4">
      <SurfaceHeader
        title={
          <span className="inline-flex items-center gap-1.5">
            Generations <Hint term="refused" />
          </span>
        }
        description="Every request for tests, and the tests it refused because they had no meaningful assertion."
      />
      <ul className="divide-y divide-hairline px-3 pb-2" data-qa="generations">
        {gens.map((g) => (
          <li key={g.id}>
            <button
              type="button"
              aria-expanded={open === g.id}
              onClick={() => setOpen(open === g.id ? null : g.id)}
              className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring"
            >
              {open === g.id ? <ChevronDownIcon className="size-4 shrink-0 text-subtle" /> : <ChevronRightIcon className="size-4 shrink-0 text-subtle" />}
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2 text-[13px]">
                  <GenerationStatusChip status={g.status} />
                  <span className="font-medium">{plural(g.accepted_count, "test")} proposed</span>
                  {g.rejected_count > 0 && (
                    <Chip tone="warning" className="bg-ember-soft text-ember">
                      <BanIcon aria-hidden />
                      {g.rejected_count} refused
                    </Chip>
                  )}
                </span>
                <span className="mt-0.5 block truncate text-[11.5px] text-subtle">
                  {g.kinds.map((k) => TEST_KIND_LABEL[k as keyof typeof TEST_KIND_LABEL] ?? k).join(", ")}
                  {g.pull_id ? ", scoped to a pull request" : g.spec_id ? ", from an OpenAPI document" : g.unit_ids.length ? `, ${plural(g.unit_ids.length, "unit")}` : ""}, {g.actor}, {formatRelative(g.created_at)}
                </span>
              </span>
            </button>
            {open === g.id && (
              <div className="px-2 pt-1 pb-4 sm:pl-9">
                <GenerationSummary g={g} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </Surface>
  );
}
