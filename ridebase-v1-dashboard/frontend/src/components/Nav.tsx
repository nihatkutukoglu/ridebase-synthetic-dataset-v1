"use client";

import { Badge, StatusDot } from "@/components/ui";
import type { Health, ModelInfo } from "@/lib/types";

export const TABS = [
  { id: "overview", label: "GENEL BAKIŞ" },
  { id: "days", label: "DAYS" },
  { id: "km", label: "KM" },
  { id: "models", label: "MODELLER" },
  { id: "features", label: "FEATURE'LAR" },
  { id: "errors", label: "HATA ANALİZİ" },
  { id: "drift", label: "DRIFT" },
  { id: "experiments", label: "DENEYLER" },
  { id: "predict", label: "CANLI TAHMİN" },
  { id: "verdict", label: "SONUÇ" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export function Logo() {
  return (
    <span className="select-none text-[15px] font-extrabold tracking-tight text-fg">
      RIDE<span className="text-rb-orange">⚡</span>BASE
    </span>
  );
}

export function Nav({
  active,
  onChange,
  health,
  info,
}: {
  active: TabId;
  onChange: (id: TabId) => void;
  health: Health | null;
  info: ModelInfo | null;
}) {
  const degraded = health?.status === "degraded";
  return (
    <header className="sticky top-0 z-40 border-b border-ink-border bg-ink-950/85 backdrop-blur">
      <div className="mx-auto flex max-w-screen flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <Logo />
          <span className="hidden text-xs text-fg-faint sm:inline">V1 Model Dashboard</span>
        </div>

        <nav
          aria-label="Bölümler"
          className="order-3 -mx-1 flex w-full gap-1 overflow-x-auto pb-1 sm:order-2 sm:w-auto sm:flex-1 sm:overflow-visible"
        >
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => onChange(t.id)}
              aria-current={active === t.id ? "page" : undefined}
              className={`whitespace-nowrap rounded-lg px-2.5 py-1.5 text-[11px] font-semibold tracking-wide transition-colors ${
                active === t.id
                  ? "bg-rb-orange-soft text-rb-orange"
                  : "text-fg-muted hover:bg-ink-700 hover:text-fg"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="order-2 ml-auto flex items-center gap-2 sm:order-3">
          <Badge tone={degraded ? "bad" : "cyan"}>
            <StatusDot tone={degraded ? "bad" : "ok"} />
            {info?.dataset_version ? `SYNTHETIC v${info.dataset_version}` : "SYNTHETIC v1.3"}
          </Badge>
          <Badge tone="warn">PROD VALIDATION: PENDING</Badge>
        </div>
      </div>
    </header>
  );
}
