"use client";

import * as React from "react";
import { Area, AreaChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";

import { CHART, ChartTooltipCard } from "@/components/charts/chart-tooltip";
import { formatDateTime, formatPercent } from "@/lib/format";

export interface CoveragePoint {
  at: string;
  percent: number;
  runId: string;
}

interface Row {
  x: string;
  percent: number;
  at: string;
}

const short = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });

/** Points in time order with a readable axis label each. */
const withSeconds = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

/** Points in time order with a readable axis label each; runs in the same minute get seconds. */
export function coverageRows(points: CoveragePoint[]): Row[] {
  const sorted = [...points].sort((a, b) => a.at.localeCompare(b.at));
  const label = (fmt: Intl.DateTimeFormat) =>
    sorted.map((p, i) => {
      const d = new Date(p.at);
      return Number.isNaN(d.getTime()) ? `Run ${i + 1}` : fmt.format(d);
    });
  let labels = label(short);
  if (new Set(labels).size < labels.length) labels = label(withSeconds);
  if (new Set(labels).size < labels.length) labels = sorted.map((_, i) => `Run ${i + 1}`);
  return sorted.map((p, i) => ({ x: labels[i] as string, percent: Math.round(p.percent * 100) / 100, at: p.at }));
}

const axisTick = { fill: CHART.axis, fontSize: 11 };

/** Line coverage after each run, oldest first. */
export function CoverageChart({ points, height = 220 }: { points: CoveragePoint[]; height?: number }) {
  const data = React.useMemo(() => coverageRows(points), [points]);
  const last = data[data.length - 1];
  const gradient = React.useId().replace(/:/g, "");
  return (
    <div
      style={{ height }}
      role="img"
      aria-label={`Line coverage over ${data.length} runs${last ? `, latest ${formatPercent(last.percent)}` : ""}`}
      className="w-full min-w-0"
      data-qa="coverage-chart"
    >
      <AreaChart responsive style={{ width: "100%", height: "100%" }} data={data} margin={{ top: 6, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={CHART.series1} stopOpacity={0.28} />
            <stop offset="100%" stopColor={CHART.series1} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} stroke={CHART.grid} />
        <XAxis dataKey="x" tickLine={false} axisLine={false} tick={axisTick} minTickGap={24} tickMargin={8} />
        <YAxis width={40} domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickLine={false} axisLine={false} tick={axisTick} tickFormatter={(v: number) => `${v}%`} />
        <Tooltip
          cursor={{ stroke: CHART.axis, strokeDasharray: "3 3" }}
          isAnimationActive={false}
          content={({ active, payload }) => {
            const p = payload?.[0]?.payload as Row | undefined;
            if (!active || !p) return null;
            return <ChartTooltipCard title={formatDateTime(p.at)} rows={[{ label: "Line coverage", value: formatPercent(p.percent), color: CHART.series1 }]} />;
          }}
        />
        <Area type="linear" dataKey="percent" stroke={CHART.series1} strokeWidth={2} fill={`url(#${gradient})`} dot={{ r: 3, fill: CHART.series1, strokeWidth: 0 }} isAnimationActive={false} />
      </AreaChart>
    </div>
  );
}
