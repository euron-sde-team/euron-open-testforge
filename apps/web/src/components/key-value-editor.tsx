"use client";

import { PlusIcon, XIcon } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface KeyValueRow {
  key: string;
  value: string;
}

export function rowsFrom(record: Record<string, unknown> | null | undefined): KeyValueRow[] {
  return Object.entries(record ?? {}).map(([key, value]) => ({ key, value: typeof value === "string" ? value : String(value ?? "") }));
}

/** Rows with an empty key are dropped; the last duplicate key wins. */
export function recordFrom(rows: KeyValueRow[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const r of rows) if (r.key.trim()) out[r.key.trim()] = r.value;
  return out;
}

/**
 * A small list of name and value pairs (HTTP headers, header to secret mappings). The
 * value can be a free text input or a picker supplied by the caller.
 */
export function KeyValueEditor({
  rows,
  onChange,
  keyPlaceholder = "Name",
  valuePlaceholder = "Value",
  addLabel = "Add",
  renderValue,
  disabled,
  label,
}: {
  rows: KeyValueRow[];
  onChange: (rows: KeyValueRow[]) => void;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
  addLabel?: string;
  renderValue?: (value: string, set: (v: string) => void, index: number) => React.ReactNode;
  disabled?: boolean;
  label: string;
}) {
  const set = (i: number, patch: Partial<KeyValueRow>) => onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input
            aria-label={`${label} ${i + 1} name`}
            className="min-w-0 flex-1 font-mono text-[12.5px]"
            placeholder={keyPlaceholder}
            value={r.key}
            disabled={disabled}
            onChange={(e) => set(i, { key: e.target.value })}
          />
          <div className="min-w-0 flex-1">
            {renderValue ? (
              renderValue(r.value, (v) => set(i, { value: v }), i)
            ) : (
              <Input
                aria-label={`${label} ${i + 1} value`}
                className="font-mono text-[12.5px]"
                placeholder={valuePlaceholder}
                value={r.value}
                disabled={disabled}
                onChange={(e) => set(i, { value: e.target.value })}
              />
            )}
          </div>
          <Button
            type="button"
            variant="subtle"
            size="icon-sm"
            aria-label={`Remove ${label} ${i + 1}`}
            disabled={disabled}
            onClick={() => onChange(rows.filter((_, j) => j !== i))}
          >
            <XIcon />
          </Button>
        </div>
      ))}
      <Button type="button" variant="ghost" size="xs" disabled={disabled} onClick={() => onChange([...rows, { key: "", value: "" }])}>
        <PlusIcon />
        {addLabel}
      </Button>
    </div>
  );
}
