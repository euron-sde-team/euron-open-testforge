"use client";

import type { InfiniteData, UseInfiniteQueryResult } from "@tanstack/react-query";
import { ScrollTextIcon, SearchIcon } from "lucide-react";
import * as React from "react";

import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Surface } from "@/components/surface";
import { TableSkeleton } from "@/components/table-skeleton";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { AuditEntry, AuditPage } from "@/lib/api/types";
import { formatDateTime, formatRelative, shortId } from "@/lib/format";

export function actionTone(action: string): "danger" | "success" | "info" | "primary" | "neutral" {
  if (/(deleted|revoked|purged|disabled|rejected|removed)/.test(action)) return "danger";
  if (/(created|approved|added)/.test(action)) return "success";
  if (/(updated|changed|published|restored)/.test(action)) return "info";
  if (/^auth\./.test(action)) return "neutral";
  return "primary";
}

export function detailsText(d: AuditEntry["details"]): string {
  const entries = Object.entries(d ?? {});
  if (!entries.length) return "";
  return entries.map(([k, v]) => `${k}: ${typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}`).join(", ");
}

/** The action filter text, debounced into the value a query uses. */
export function useActionFilter(): [string, string, (v: string) => void] {
  const [input, setInput] = React.useState("");
  const [action, setAction] = React.useState("");
  React.useEffect(() => {
    const t = setTimeout(() => setAction(input.trim()), 350);
    return () => clearTimeout(t);
  }, [input]);
  return [input, action, setInput];
}

/** A filterable, paged audit log: the instance log and an organization's log look the same. */
export function AuditLogPanel({
  query: q,
  input,
  action,
  setInput,
  emptyText,
}: {
  query: UseInfiniteQueryResult<InfiniteData<AuditPage>>;
  input: string;
  action: string;
  setInput: (v: string) => void;
  emptyText: string;
}) {
  const rows = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <>
      <div className="relative mb-3 w-full sm:w-72">
        <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Filter by action, like run.finished" aria-label="Filter by action" className="pl-9" />
      </div>
      <Surface className="overflow-hidden">
        {q.isPending ? (
          <div className="pt-3">
            <TableSkeleton rows={8} cols={4} />
          </div>
        ) : q.isError && !q.data ? (
          <ErrorState error={q.error} title="The audit log could not be loaded" onRetry={() => void q.refetch()} />
        ) : !rows.length ? (
          <EmptyState
            icon={ScrollTextIcon}
            title={action ? "No entries for this action" : "Nothing audited yet"}
            description={action ? "Action names look like run.finished or import.created. Clear the filter to see everything." : emptyText}
            action={
              action ? (
                <Button variant="outline" size="sm" onClick={() => setInput("")}>
                  Clear filter
                </Button>
              ) : undefined
            }
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead className="hidden md:table-cell">Actor</TableHead>
                  <TableHead className="hidden lg:table-cell">Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap">
                      <div className="tabular">{formatDateTime(e.at)}</div>
                      <div className="text-[11px] text-subtle">{formatRelative(e.at)}</div>
                    </TableCell>
                    <TableCell>
                      <Chip tone={actionTone(e.action)} className="font-mono">
                        {e.action}
                      </Chip>
                      {e.target_type && (
                        <div className="mt-1 text-[11.5px] text-subtle">
                          {e.target_type}
                          {e.target_id ? <span className="font-mono"> {shortId(e.target_id)}</span> : null}
                        </div>
                      )}
                      <div className="mt-0.5 truncate text-[11.5px] text-muted-foreground md:hidden">{e.actor_email ?? "System"}</div>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <div className="truncate">{e.actor_email ?? "System"}</div>
                      {e.ip && <div className="font-mono text-[11px] text-subtle">{e.ip}</div>}
                    </TableCell>
                    <TableCell className="hidden max-w-[320px] lg:table-cell">
                      <div className="truncate text-[12px] text-muted-foreground" title={detailsText(e.details)}>
                        {detailsText(e.details) || <span className="text-faint">No details</span>}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-between px-5 py-3 text-xs text-muted-foreground">
              <span>{rows.length} entries</span>
              {q.hasNextPage ? (
                <Button variant="outline" size="sm" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage}>
                  {q.isFetchingNextPage ? "Loading..." : "Load older"}
                </Button>
              ) : (
                <span>Beginning of the log</span>
              )}
            </div>
          </>
        )}
      </Surface>
    </>
  );
}
