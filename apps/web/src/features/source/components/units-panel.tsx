"use client";

import { CheckIcon, CircleAlertIcon, FlaskConicalIcon, ListTreeIcon } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { CodeView } from "@/components/code-view";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Hint } from "@/components/hint";
import { CoverageBar } from "@/components/status-chips";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Dialog, DialogBody, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { SimpleSelect } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { GenerateDialog, type GenerateScope } from "@/features/tests/components/generate-dialog";
import type { Unit } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { formatPercent, plural } from "@/lib/format";
import { UNIT_KIND_LABEL, unitKindLabel, unitTestState } from "@/lib/status";

import { useUnit, useUnits } from "../api";

/** Every unit of an import, filterable to the untested ones, and a way to generate tests for a selection. */
export function UnitsPanel({ pid, iid, canGenerate, canAdmin }: { pid: string; iid: string; canGenerate: boolean; canAdmin: boolean }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const untested = params.get("untested") === "1";
  const kind = params.get("kind") ?? "";
  const q = useUnits(pid, iid, { untested, kind });
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [scope, setScope] = React.useState<GenerateScope | null>(null);
  const list = q.data ?? [];

  React.useEffect(() => setSelected(new Set()), [untested, kind, iid]);

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params.toString());
    next.set("tab", "units");
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  const chosen = list.filter((u) => selected.has(u.id));
  const target = chosen.length ? chosen : list;
  const allOn = list.length > 0 && chosen.length === list.length;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <SimpleSelect
            aria-label="Kind"
            className="w-44"
            value={kind}
            onValueChange={(v) => setParam("kind", v || null)}
            options={[{ value: "", label: "Every kind" }, ...Object.entries(UNIT_KIND_LABEL).map(([value, label]) => ({ value, label: `${label}s` }))]}
          />
          <label className="inline-flex items-center gap-2 text-[13px] text-muted-foreground">
            <Switch checked={untested} onCheckedChange={(on) => setParam("untested", on ? "1" : null)} aria-label="Only untested units" />
            Only untested <Hint term="untested" />
          </label>
        </div>
        {canGenerate && list.length > 0 && (
          <Button
            onClick={() =>
              setScope({
                unitIds: target.map((u) => u.id),
                label: `Tests for ${plural(target.length, "unit")}${chosen.length ? " you selected" : untested ? " no test refers to" : ""}.`,
              })
            }
            data-qa="generate-for-units"
          >
            <FlaskConicalIcon />
            {chosen.length ? `Generate tests for ${plural(chosen.length, "unit")}` : list.length === 1 ? "Generate tests for this unit" : `Generate tests for these ${list.length}`}
          </Button>
        )}
      </div>
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={6} cols={4} />
          </div>
        ) : q.isError ? (
          <ErrorState error={q.error} onRetry={() => void q.refetch()} />
        ) : !list.length ? (
          <EmptyState
            icon={ListTreeIcon}
            title={untested ? "Every unit is referenced by a test" : "No units found"}
            description={
              untested
                ? "Nothing in this import is untested. Turn the filter off to see every unit and its coverage."
                : "TestForge found no functions, classes, methods or routes in this import. Check that it holds Python or JavaScript and TypeScript source."
            }
            action={
              untested || kind ? (
                <Button variant="outline" size="sm" onClick={() => router.replace(`${pathname}?tab=units`, { scroll: false })}>
                  Show every unit
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            {canGenerate && (
              <div className="flex items-center gap-3 px-5 pt-3 pb-1 text-[12.5px] text-muted-foreground">
                <SelectBox on={allOn} label="Select every unit" onToggle={() => setSelected(allOn ? new Set() : new Set(list.map((u) => u.id)))} />
                {chosen.length ? `${chosen.length} selected` : `${plural(list.length, "unit")}`}
              </div>
            )}
            <div className="px-3 pb-3">
              <UnitList
                pid={pid}
                iid={iid}
                units={list}
                canGenerate={canGenerate}
                canAdmin={canAdmin}
                selected={canGenerate ? selected : undefined}
                onToggle={(id) =>
                  setSelected((cur) => {
                    const next = new Set(cur);
                    if (next.has(id)) next.delete(id);
                    else next.add(id);
                    return next;
                  })
                }
              />
            </div>
          </>
        )}
      </Surface>
      {scope && <GenerateDialog pid={pid} open={!!scope} onOpenChange={(o) => !o && setScope(null)} scope={scope} canAdmin={canAdmin} />}
    </div>
  );
}

function SelectBox({ on, label, onToggle }: { on: boolean; label: string; onToggle: () => void }) {
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

/** Units as rows; click one to read its source. */
export function UnitList({
  pid,
  iid,
  units,
  canGenerate,
  canAdmin,
  selected,
  onToggle,
}: {
  pid: string;
  iid: string;
  units: Unit[];
  canGenerate: boolean;
  canAdmin: boolean;
  selected?: Set<string>;
  onToggle?: (id: string) => void;
}) {
  const [open, setOpen] = React.useState<Unit | null>(null);
  return (
    <>
      <ul className="divide-y divide-hairline" data-qa="units">
        {units.map((u) => (
          <li key={u.id} className="flex items-center gap-3 px-2 py-2.5" data-qa="unit">
            {selected && onToggle && <SelectBox on={selected.has(u.id)} label={`Select ${u.name}`} onToggle={() => onToggle(u.id)} />}
            <button type="button" onClick={() => setOpen(u)} className="min-w-0 flex-1 rounded-lg text-left focus-visible:outline-2 focus-visible:outline-ring">
              <span className="flex flex-wrap items-center gap-2">
                <Chip tone="neutral">{unitKindLabel(u.kind)}</Chip>
                <span className="font-mono text-[13px] font-medium break-all">{u.name}</span>
                {unitTestState(u) === "untested" && (
                  <Chip tone="warning" data-qa="unreferenced">
                    <CircleAlertIcon aria-hidden />
                    Not referenced by any test
                  </Chip>
                )}
                {unitTestState(u) === "generated-only" && (
                  <Chip tone="info" title="No test in the repository refers to it; TestForge's generated tests cover it.">
                    Covered by generated tests
                  </Chip>
                )}
              </span>
              <span className="mt-0.5 block truncate font-mono text-[11.5px] text-subtle">
                {u.file}:{u.start_line} to {u.end_line}
              </span>
            </button>
            <span className="hidden w-32 shrink-0 sm:block">
              <span className="tabular block text-right text-[12px] font-medium">{u.covered_percent == null ? "Not measured" : formatPercent(u.covered_percent)}</span>
              <CoverageBar percent={u.covered_percent} className="mt-1" />
            </span>
          </li>
        ))}
      </ul>
      <UnitDialog pid={pid} iid={iid} unit={open} onClose={() => setOpen(null)} canGenerate={canGenerate} canAdmin={canAdmin} />
    </>
  );
}

function UnitDialog({ pid, iid, unit, onClose, canGenerate, canAdmin }: { pid: string; iid: string; unit: Unit | null; onClose: () => void; canGenerate: boolean; canAdmin: boolean }) {
  const q = useUnit(pid, iid, unit?.id);
  const [generating, setGenerating] = React.useState(false);
  return (
    <>
      <Dialog open={!!unit && !generating} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="font-mono break-all">{unit?.qualname}</DialogTitle>
            <DialogDescription>
              {unit ? `${unitKindLabel(unit.kind)} in ${unit.file}, lines ${unit.start_line} to ${unit.end_line}. ` : ""}
              {unit?.covered_percent != null ? `${formatPercent(unit.covered_percent)} of its lines ran in the latest run.` : "Not measured by a run yet."}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="space-y-3">
            {unit?.signature && <p className="rounded-lg bg-muted px-3 py-2 font-mono text-[12.5px] break-all">{unit.signature}</p>}
            {q.isPending ? (
              <TableSkeleton rows={4} cols={1} />
            ) : q.isError ? (
              <ErrorState compact error={q.error} />
            ) : q.data ? (
              <CodeView code={q.data.source} language={q.data.language} startLine={q.data.start_line} label="Source" maxHeight="24rem" />
            ) : null}
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
            {canGenerate && unit && (
              <Button onClick={() => setGenerating(true)}>
                <FlaskConicalIcon />
                Generate tests for this {unitKindLabel(unit.kind).toLowerCase()}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {unit && generating && (
        <GenerateDialog
          pid={pid}
          open={generating}
          onOpenChange={(o) => {
            if (!o) {
              setGenerating(false);
              onClose();
            }
          }}
          scope={{ unitIds: [unit.id], label: `Tests for ${unit.qualname}.` }}
          canAdmin={canAdmin}
        />
      )}
    </>
  );
}
