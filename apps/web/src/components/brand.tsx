import { cn } from "@/lib/cn";

/** The TestForge mark: a check forged inside a hexagon (a passing test, made solid). */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 44 44" aria-hidden className={cn("size-7", className)}>
      <path d="M22 2.5 39 12.25v19.5L22 41.5 5 31.75v-19.5Z" className="fill-primary" />
      <path d="M22 8.5 33.8 15.25v13.5L22 35.5 10.2 28.75v-13.5Z" className="fill-primary-foreground" opacity="0.14" />
      <path d="m14.5 22.5 5 5 10-11" fill="none" className="stroke-primary-foreground" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function BrandLogo({ collapsed = false, className }: { collapsed?: boolean; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <BrandMark />
      {!collapsed && <span className="text-[15px] font-semibold tracking-[-0.02em]">TestForge</span>}
    </span>
  );
}
