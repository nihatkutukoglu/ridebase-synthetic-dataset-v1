"use client";

import { ReactNode, useState } from "react";
import { ApiError } from "@/lib/api";

/* ------------------------------------------------------------------ Card */
export function Card({
  children,
  className = "",
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section";
}) {
  const Tag = as;
  return (
    <Tag
      className={`rounded-2xl border border-ink-border bg-ink-800/70 backdrop-blur-sm ${className}`}
    >
      {children}
    </Tag>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  desc,
}: {
  eyebrow?: string;
  title: string;
  desc?: string;
}) {
  return (
    <header className="mb-5">
      {eyebrow && <div className="label-tiny mb-1 text-rb-orange">{eyebrow}</div>}
      <h2 className="text-xl font-semibold text-fg sm:text-2xl">{title}</h2>
      {desc && <p className="mt-1 max-w-2xl text-sm text-fg-muted">{desc}</p>}
    </header>
  );
}

/* ------------------------------------------------------------------ Metric */
export function MetricCard({
  label,
  value,
  sub,
  accent = "orange",
  tip,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: "orange" | "cyan" | "plain";
  tip?: string;
}) {
  const bar =
    accent === "orange" ? "bg-rb-orange" : accent === "cyan" ? "bg-rb-cyan" : "bg-ink-border";
  return (
    <Card className="relative overflow-hidden p-4">
      <div className={`absolute left-0 top-0 h-full w-[3px] ${bar}`} />
      <div className="flex items-center gap-1.5">
        <span className="label-tiny">{label}</span>
        {tip && <InfoTip text={tip} />}
      </div>
      <div className="metric-num mt-2 text-2xl font-semibold text-fg sm:text-[28px]">{value}</div>
      {sub && <div className="mt-1 text-xs text-fg-muted">{sub}</div>}
    </Card>
  );
}

/* ------------------------------------------------------------------ Badge / Pill */
const tone: Record<string, string> = {
  ok: "text-ok border-ok/30 bg-ok/10",
  warn: "text-warn border-warn/30 bg-warn/10",
  bad: "text-bad border-bad/30 bg-bad/10",
  orange: "text-rb-orange border-rb-orange/30 bg-rb-orange-soft",
  cyan: "text-rb-cyan border-rb-cyan/30 bg-rb-cyan-soft",
  neutral: "text-fg-muted border-ink-border bg-ink-700",
};

export function Badge({
  children,
  tone: t = "neutral",
}: {
  children: ReactNode;
  tone?: keyof typeof tone;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${tone[t]}`}
    >
      {children}
    </span>
  );
}

export function StatusDot({ tone: t = "ok" }: { tone?: "ok" | "warn" | "bad" }) {
  const c = t === "ok" ? "bg-ok" : t === "warn" ? "bg-warn" : "bg-bad";
  return <span className={`inline-block h-2 w-2 rounded-full ${c}`} aria-hidden />;
}

/* ------------------------------------------------------------------ InfoTip */
export function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-label={text}
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-ink-border text-[10px] font-bold text-fg-faint hover:text-fg"
      >
        i
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-1/2 top-6 z-30 w-56 -translate-x-1/2 rounded-lg border border-ink-border bg-ink-850 p-2.5 text-[11px] font-normal leading-relaxed text-fg-muted shadow-xl"
        >
          {text}
        </span>
      )}
    </span>
  );
}

/* ------------------------------------------------------------------ DataTable */
export function DataTable({
  columns,
  rows,
  highlight,
}: {
  columns: { key: string; label: string; fmt?: (v: unknown, row: Record<string, unknown>) => ReactNode; align?: "left" | "right" }[];
  rows: Record<string, unknown>[];
  highlight?: (row: Record<string, unknown>) => boolean;
}) {
  if (!rows.length) return <EmptyState note="No rows in this artifact." />;
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[560px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-ink-border">
            {columns.map((c) => (
              <th
                key={c.key}
                className={`label-tiny px-3 py-2 font-semibold ${
                  c.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              className={`border-b border-ink-border/50 ${
                highlight?.(row) ? "bg-rb-orange-soft" : "hover:bg-ink-700/40"
              }`}
            >
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={`px-3 py-2 ${
                    c.align === "right" ? "text-right metric-num" : "text-fg"
                  }`}
                >
                  {c.fmt ? c.fmt(row[c.key], row) : String(row[c.key] ?? "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ states */
export function Loading({ label = "Yükleniyor…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-ink-border bg-ink-800/60 p-6 text-sm text-fg-muted">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-border border-t-rb-orange" />
      {label}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: Error | ApiError | null; onRetry?: () => void }) {
  const offline = error instanceof ApiError ? false : true;
  return (
    <div className="rounded-2xl border border-bad/30 bg-bad/5 p-6 text-sm">
      <div className="font-semibold text-bad">
        {offline ? "API'ye ulaşılamıyor" : `İstek başarısız (${(error as ApiError)?.status ?? "?"})`}
      </div>
      <p className="mt-1 text-fg-muted">
        {offline
          ? "Backend çalışıyor mu? NEXT_PUBLIC_API_BASE_URL doğru mu?"
          : String((error as ApiError)?.detail ?? error?.message ?? "Bilinmeyen hata")}
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-lg border border-ink-border px-3 py-1.5 text-xs font-semibold text-fg hover:border-rb-orange"
        >
          Tekrar dene
        </button>
      )}
    </div>
  );
}

export function EmptyState({ note = "Artifact not available" }: { note?: string }) {
  return (
    <div className="rounded-xl border border-dashed border-ink-border bg-ink-850/50 p-5 text-center text-sm text-fg-faint">
      {note}
    </div>
  );
}

/* ------------------------------------------------------------------ misc */
export function KeyVal({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-ink-border/50 py-1.5 last:border-0">
      <span className="text-xs text-fg-muted">{k}</span>
      <span className="metric-num text-right text-sm text-fg">{v}</span>
    </div>
  );
}
