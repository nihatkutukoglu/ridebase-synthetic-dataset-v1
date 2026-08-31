"use client";

import { useEffect, useState } from "react";
import { Nav, TABS, type TabId } from "@/components/Nav";
import {
  DriftSection,
  ErrorsSection,
  ExperimentsSection,
  FeaturesSection,
  ModelsSection,
  OverviewSection,
  TargetSection,
  VerdictSection,
} from "@/components/sections/analytics";
import { LivePredictionSection } from "@/components/sections/LivePrediction";
import { ErrorState } from "@/components/ui";
import { useApi } from "@/lib/api";
import type { Health, ModelInfo } from "@/lib/types";

const IDS = TABS.map((t) => t.id);

export default function Page() {
  const [tab, setTab] = useState<TabId>("overview");
  const { data: health, error: healthError, reload } = useApi<Health>("/health");
  const { data: info } = useApi<ModelInfo>("/api/v1/model/info");

  useEffect(() => {
    const fromHash = () => {
      const h = window.location.hash.replace("#", "") as TabId;
      if (IDS.includes(h)) setTab(h);
    };
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

  const go = (id: TabId) => {
    setTab(id);
    window.location.hash = id;
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div className="min-h-screen">
      <Nav active={tab} onChange={go} health={health} info={info} />

      <main className="mx-auto max-w-screen px-4 py-6 sm:px-6 sm:py-8">
        {healthError && (
          <div className="mb-6">
            <ErrorState error={healthError} onRetry={reload} />
          </div>
        )}
        {health?.status === "degraded" && (
          <div className="mb-6 rounded-xl border border-warn/40 bg-warn/5 p-3 text-sm text-warn">
            API DEGRADED — {health.errors?.join("; ") || "model yükleme sorunu"}
          </div>
        )}

        {tab === "overview" && <OverviewSection info={info} />}
        {tab === "days" && <TargetSection target="DAYS" />}
        {tab === "km" && <TargetSection target="KM" />}
        {tab === "models" && <ModelsSection />}
        {tab === "features" && <FeaturesSection />}
        {tab === "errors" && <ErrorsSection />}
        {tab === "drift" && <DriftSection />}
        {tab === "experiments" && <ExperimentsSection />}
        {tab === "predict" && <LivePredictionSection />}
        {tab === "verdict" && <VerdictSection info={info} />}
      </main>

      <footer className="mx-auto max-w-screen px-4 py-8 text-center text-[11px] text-fg-faint sm:px-6">
        RideBase V1 Intelligence · model: {info?.model_generation ?? "…"} · dataset v
        {info?.dataset_version ?? "1.3"} · synthetic validation only — real fleet validation pending
      </footer>
    </div>
  );
}
