import * as React from "react";

import { cn } from "@/lib/cn";

/** Label and value pairs in a responsive grid, for run headers and detail panels. */
export function MetaList({ items, className }: { items: { label: React.ReactNode; value: React.ReactNode; hint?: React.ReactNode }[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-6", className)}>
      {items.map((item, i) => (
        <div key={i} className="min-w-0">
          <dt className="flex items-center gap-1 text-[11.5px] font-medium text-muted-foreground">
            {item.label}
            {item.hint}
          </dt>
          <dd className="tabular mt-0.5 truncate text-[14px] font-semibold text-foreground">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
