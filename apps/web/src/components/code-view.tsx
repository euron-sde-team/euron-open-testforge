"use client";

import * as React from "react";

import { CopyButton } from "@/components/copy-button";
import { cn } from "@/lib/cn";
import { highlightCode, type TokenType } from "@/lib/code";

const TOKEN_CLASS: Record<TokenType, string> = {
  keyword: "text-code-keyword",
  string: "text-code-string",
  comment: "text-code-comment italic",
  number: "text-code-number",
  function: "text-code-function",
  decorator: "text-code-decorator",
  plain: "",
};

export type LineMark = "covered" | "missing" | "changed" | "focus";

const MARK_CLASS: Record<LineMark, string> = {
  covered: "bg-code-covered",
  missing: "bg-code-missing",
  changed: "bg-code-changed",
  focus: "bg-white/[0.07]",
};

const MARK_GUTTER: Record<LineMark, string> = {
  covered: "shadow-[inset_3px_0_0_var(--series-1)]",
  missing: "shadow-[inset_3px_0_0_var(--danger)]",
  changed: "shadow-[inset_3px_0_0_var(--warning)]",
  focus: "shadow-[inset_3px_0_0_var(--code-muted)]",
};

/**
 * Code with line numbers and syntax highlighting, on a dark slab in both themes. Lines can
 * be marked (covered, missing, changed) so coverage and diffs read at a glance; marks are
 * a fill and a gutter bar, and each marked line has a text label for screen readers.
 */
export function CodeView({
  code,
  language,
  label,
  startLine = 1,
  marks,
  className,
  maxHeight,
}: {
  code: string;
  language: string | null | undefined;
  label?: string;
  startLine?: number;
  marks?: (line: number) => LineMark | null;
  className?: string;
  maxHeight?: string;
}) {
  const lines = React.useMemo(() => code.replace(/\n$/, "").split("\n"), [code]);
  const tokens = React.useMemo(() => highlightCode(code.replace(/\n$/, ""), language ?? null), [code, language]);
  const width = String(startLine + lines.length).length;
  return (
    <div className={cn("min-w-0 overflow-hidden rounded-xl bg-code-bg text-code-fg", className)} data-qa="code-view">
      <div className="flex items-center justify-between gap-2 px-3.5 pt-2 pb-1">
        <span className="truncate text-[10.5px] font-semibold tracking-[0.06em] text-code-muted uppercase">{label ?? language ?? ""}</span>
        <CopyButton value={code} iconOnly label={`Copy ${label ?? "code"}`} variant="ghost" className="text-code-muted hover:bg-white/10 hover:text-code-fg" />
      </div>
      <div className="overflow-auto pb-3" style={maxHeight ? { maxHeight } : undefined} tabIndex={0} role="region" aria-label={label ?? "Code"}>
        <pre className="min-w-max font-mono text-[12px] leading-[1.65]">
          {lines.map((line, i) => {
            const n = startLine + i;
            const mark = marks?.(n) ?? null;
            return (
              <div key={i} className={cn("flex pr-4", mark && MARK_CLASS[mark], mark && MARK_GUTTER[mark])} data-line={n} data-mark={mark ?? undefined}>
                <span className="w-[calc(var(--w)*1ch+1.75rem)] shrink-0 pr-3 pl-3.5 text-right text-code-muted/70 select-none" style={{ ["--w" as string]: width }}>
                  {n}
                </span>
                {mark && mark !== "focus" && <span className="sr-only">{mark} line: </span>}
                <code>
                  {(tokens[i] ?? []).map((t, j) => (
                    <span key={j} className={TOKEN_CLASS[t.type]}>
                      {t.text}
                    </span>
                  ))}
                  {line.length === 0 && " "}
                </code>
              </div>
            );
          })}
        </pre>
      </div>
    </div>
  );
}

/** The legend under a marked code view. */
export function CodeLegend({ items }: { items: { mark: LineMark; label: string }[] }) {
  const swatch: Record<LineMark, string> = { covered: "bg-series-1", missing: "bg-danger", changed: "bg-warning", focus: "bg-subtle" };
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted-foreground">
      {items.map((i) => (
        <li key={i.mark} className="flex items-center gap-1.5">
          <span className={cn("h-3 w-1 rounded-full", swatch[i.mark])} aria-hidden />
          {i.label}
        </li>
      ))}
    </ul>
  );
}
