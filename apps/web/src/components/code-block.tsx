"use client";

import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import * as React from "react";

import { CopyButton } from "@/components/copy-button";
import { cn } from "@/lib/cn";

/** Pretty JSON for display; strings pass through, undefined shows as nothing. */
export function prettyJson(value: unknown): string {
  if (value === undefined) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * A dark code slab (the same in both themes) with a copy button. Long content starts
 * collapsed to a few lines and opens on demand, so a timeline of tool results stays
 * scannable.
 */
export function CodeBlock({
  value,
  label,
  className,
  maxLines = 14,
  wrap = true,
}: {
  value: string;
  label?: string;
  className?: string;
  maxLines?: number;
  wrap?: boolean;
}) {
  const lines = value.split("\n").length;
  const long = lines > maxLines || value.length > maxLines * 120;
  const [open, setOpen] = React.useState(!long);
  return (
    <div className={cn("group/code relative min-w-0 overflow-hidden rounded-xl bg-code-bg text-code-fg", className)}>
      <div className="flex items-center justify-between gap-2 px-3.5 pt-2">
        <span className="text-[10.5px] font-semibold tracking-[0.06em] text-code-muted uppercase">{label ?? ""}</span>
        <CopyButton value={value} iconOnly label={`Copy ${label ?? "text"}`} variant="ghost" className="text-code-muted hover:bg-white/10 hover:text-code-fg" />
      </div>
      <pre
        className={cn(
          "overflow-x-auto px-3.5 pt-1 pb-3 font-mono text-[12px] leading-relaxed",
          wrap && "break-words whitespace-pre-wrap",
          !open && "max-h-[11.5rem] overflow-hidden",
        )}
      >
        {value || " "}
      </pre>
      {long && (
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className={cn(
            "flex w-full items-center justify-center gap-1 py-1.5 text-[11.5px] font-medium text-code-muted hover:text-code-fg focus-visible:outline-2 focus-visible:outline-ring",
            !open && "absolute inset-x-0 bottom-0 bg-gradient-to-t from-code-bg via-code-bg/95 to-transparent pt-6",
          )}
        >
          {open ? <ChevronDownIcon className="size-3.5" /> : <ChevronRightIcon className="size-3.5" />}
          {open ? "Show less" : `Show all ${lines} lines`}
        </button>
      )}
    </div>
  );
}

export function JsonBlock({ value, label, className, maxLines }: { value: unknown; label?: string; className?: string; maxLines?: number }) {
  return <CodeBlock value={prettyJson(value)} label={label} className={className} maxLines={maxLines} />;
}
