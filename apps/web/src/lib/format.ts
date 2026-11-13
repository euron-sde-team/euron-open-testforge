/** Number and date formatting used everywhere a figure is shown. */

const intFmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

function trim(n: number): string {
  const fixed = n >= 100 ? n.toFixed(0) : n.toFixed(1);
  return fixed.replace(/\.0$/, "");
}

/** 14,923. */
export function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return intFmt.format(value);
}

/** A 0..1 ratio as a percentage: 0.2462 becomes 24.6%. */
export function formatRatio(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return formatPercent(value * 100, digits);
}

/** A value already in percent: 60.4 becomes 60.4%. Whole numbers drop the decimal. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  const fixed = value.toFixed(digits);
  return `${fixed.replace(/\.0+$/, "")}%`;
}

/** 812 B, 4.2 KB, 12 MB. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || !Number.isFinite(bytes)) return "n/a";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${trim(bytes / 1024)} KB`;
  return `${trim(bytes / (1024 * 1024))} MB`;
}

const dateTimeFmt = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" });
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "n/a" : dateTimeFmt.format(d);
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "n/a" : dateFmt.format(d);
}

/** "just now", "5m ago", "3h ago", "2d ago", then a date. */
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "Never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "n/a";
  const diff = Math.round((now.getTime() - d.getTime()) / 1000);
  const future = diff < 0;
  const s = Math.abs(diff);
  const wrap = (v: string) => (future ? `in ${v}` : `${v} ago`);
  if (s < 45) return future ? "in a moment" : "just now";
  if (s < 3600) return wrap(`${Math.max(1, Math.round(s / 60))}m`);
  if (s < 86_400) return wrap(`${Math.round(s / 3600)}h`);
  if (s < 86_400 * 14) return wrap(`${Math.round(s / 86_400)}d`);
  return formatDate(iso);
}

/** Initials for an avatar: "Avery Chen" becomes "AC". */
export function initials(name: string | null | undefined): string {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? "") : "";
  return (first + last).toUpperCase() || "?";
}

/** 1.2K, 3.4M: compact counts for tiles and axes. */
export function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "n/a";
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

/** 840 ms, 2.4 s, 3m 10s. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return "n/a";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1).replace(/\.0$/, "")} s`;
  const m = Math.floor(ms / 60_000);
  return `${m}m ${Math.round((ms % 60_000) / 1000)}s`;
}

/** "1 row", "2,000 rows": a count with its noun in the right number. */
export function plural(n: number | null | undefined, noun: string, nouns = `${noun}s`): string {
  return `${formatNumber(n)} ${n === 1 ? noun : nouns}`;
}

/** Money and counts from the API arrive as numbers or decimal strings; both become a number (or null). */
export function toNumber(value: number | string | null | undefined): number | null {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

/** A short id for display: the first 8 characters of a UUID. */
export function shortId(id: string | null | undefined): string {
  return id ? id.slice(0, 8) : "n/a";
}

/** "Mar 4": a day label for chart axes (the day string is YYYY-MM-DD in UTC). */
export function shortDay(day: string): string {
  const d = new Date(`${day.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return day;
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(d);
}

/** Bytes, seconds and the like are fine; this one is for a 0..1 share shown as a bar width. */
export function clampPct(value: number | null | undefined): number {
  if (value == null || !Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

/** Peak memory reported in kilobytes: 64,744 KB becomes 63.2 MB. */
export function formatMemoryKb(kb: number | null | undefined): string {
  if (kb == null || !Number.isFinite(kb)) return "n/a";
  return formatBytes(kb * 1024);
}

/** A limit in seconds: 120 becomes "120 s", 3600 becomes "60m 0s". */
export function formatSeconds(s: number | null | undefined): string {
  if (s == null || !Number.isFinite(s)) return "n/a";
  return s <= 300 ? `${s} s` : formatDuration(s * 1000);
}

/** The short form of a commit hash. */
export function shortSha(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 7) : "n/a";
}
