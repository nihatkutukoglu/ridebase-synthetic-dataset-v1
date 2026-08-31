"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

const ORANGE = "#ff6a1a";
const CYAN = "#22d3ee";
const GRID = "#1b1f27";

export function ChartFrame({ height = 300, children }: { height?: number; children: React.ReactElement }) {
  return (
    <div style={{ width: "100%", height }}>
      <ResponsiveContainer>{children}</ResponsiveContainer>
    </div>
  );
}

/* ------------------------------------------------ actual vs predicted / residual */
export function ScatterPlot({
  data,
  xKey,
  yKey,
  xLabel,
  yLabel,
  unit,
  refLine = "diagonal",
  height = 320,
}: {
  data: Record<string, number>[];
  xKey: string;
  yKey: string;
  xLabel: string;
  yLabel: string;
  unit: string;
  refLine?: "diagonal" | "zero";
  height?: number;
}) {
  const xs = data.map((d) => d[xKey]);
  const max = Math.max(...xs, ...data.map((d) => d[yKey]));
  return (
    <ChartFrame height={height}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis
          type="number"
          dataKey={xKey}
          name={xLabel}
          unit={unit}
          tickFormatter={(v) => `${Math.round(v)}`}
          label={{ value: xLabel, position: "insideBottom", offset: -12, fill: "#5b6472", fontSize: 11 }}
        />
        <YAxis
          type="number"
          dataKey={yKey}
          name={yLabel}
          tickFormatter={(v) => `${Math.round(v)}`}
          label={{ value: yLabel, angle: -90, position: "insideLeft", fill: "#5b6472", fontSize: 11 }}
        />
        <ZAxis range={[10, 10]} />
        <Tooltip formatter={(v: number) => `${Math.round(v)} ${unit}`} cursor={{ stroke: GRID }} />
        {refLine === "diagonal" ? (
          <ReferenceLine
            segment={[
              { x: 0, y: 0 },
              { x: max, y: max },
            ]}
            stroke={CYAN}
            strokeDasharray="4 4"
          />
        ) : (
          <ReferenceLine y={0} stroke={CYAN} strokeDasharray="4 4" />
        )}
        <Scatter data={data} fill={ORANGE} fillOpacity={0.35} />
      </ScatterChart>
    </ChartFrame>
  );
}

/* ------------------------------------------------ histogram */
export function Histogram({
  bins,
  unit,
  color = ORANGE,
  height = 260,
}: {
  bins: { x0: number; x1: number; count: number }[];
  unit: string;
  color?: string;
  height?: number;
}) {
  const data = bins.map((b) => ({ mid: (b.x0 + b.x1) / 2, count: b.count }));
  return (
    <ChartFrame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 20, left: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis
          dataKey="mid"
          tickFormatter={(v) => `${Math.round(v)}`}
          label={{ value: unit, position: "insideBottom", offset: -10, fill: "#5b6472", fontSize: 11 }}
        />
        <YAxis allowDecimals={false} />
        <Tooltip formatter={(v: number) => [`${v}`, "count"]} labelFormatter={(l) => `~${Math.round(l as number)} ${unit}`} />
        <Bar dataKey="count" fill={color} radius={[2, 2, 0, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

/* ------------------------------------------------ tolerance bars */
export function ToleranceBars({
  data,
  height = 260,
}: {
  data: { label: string; value: number }[];
  height?: number;
}) {
  return (
    <ChartFrame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" />
        <YAxis domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
        <Tooltip formatter={(v: number) => `${(v * 100).toFixed(1)}%`} />
        <Bar dataKey="value" fill={ORANGE} radius={[3, 3, 0, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={i % 2 ? ORANGE : "#ff8748"} />
          ))}
        </Bar>
      </BarChart>
    </ChartFrame>
  );
}

/* ------------------------------------------------ horizontal bars (importance) */
export function HBar({
  data,
  unit = "",
  color = ORANGE,
  height,
}: {
  data: { label: string; value: number }[];
  unit?: string;
  color?: string;
  height?: number;
}) {
  const h = height ?? Math.max(180, data.length * 26 + 40);
  return (
    <ChartFrame height={h}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 8 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tickFormatter={(v) => `${v}${unit}`} />
        <YAxis type="category" dataKey="label" width={168} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v: number) => `${typeof v === "number" ? v.toFixed(3) : v}${unit}`} />
        <Bar dataKey="value" fill={color} radius={[0, 3, 3, 0]} />
      </BarChart>
    </ChartFrame>
  );
}

/* ------------------------------------------------ grouped bars (drift / compare) */
export function GroupedBars({
  data,
  keys,
  height = 300,
  colors = [ORANGE, CYAN, "#a78bfa"],
}: {
  data: Record<string, string | number>[];
  keys: string[];
  height?: number;
  colors?: string[];
}) {
  return (
    <ChartFrame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" />
        <YAxis />
        <Tooltip />
        <Legend />
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} fill={colors[i % colors.length]} radius={[3, 3, 0, 0]} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

/* ------------------------------------------------ line history (optuna / evolution) */
export function LineHistory({
  data,
  lines,
  xKey = "trial",
  height = 280,
  yLabel,
}: {
  data: Record<string, number>[];
  lines: { key: string; label: string; color?: string }[];
  xKey?: string;
  height?: number;
  yLabel?: string;
}) {
  return (
    <ChartFrame height={height}>
      <LineChart data={data} margin={{ top: 8, right: 20, bottom: 16, left: 8 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis dataKey={xKey} />
        <YAxis label={yLabel ? { value: yLabel, angle: -90, position: "insideLeft", fill: "#5b6472", fontSize: 11 } : undefined} />
        <Tooltip />
        <Legend />
        {lines.map((l, i) => (
          <Line
            key={l.key}
            type="monotone"
            dataKey={l.key}
            name={l.label}
            stroke={l.color ?? [ORANGE, CYAN][i % 2]}
            dot={false}
            strokeWidth={2}
          />
        ))}
      </LineChart>
    </ChartFrame>
  );
}
