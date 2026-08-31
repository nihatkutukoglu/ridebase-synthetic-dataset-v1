import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import { Nav } from "@/components/Nav";
import { ErrorState, MetricCard } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { OverviewSection } from "@/components/sections/analytics";
import { LivePredictionSection } from "@/components/sections/LivePrediction";

const OVERVIEW = {
  available: true,
  kpis: { km_r2: 0.46, km_mae: 940, days_r2: 0.67, days_mae: 22, days_within_30: 0.78 },
  status_card: { synthetic_validation: "PASS", leakage_audit: "PASS" },
  baseline_vs_final: { rows: [] },
};
const FEATURES = {
  count: 2,
  feature_count_days: 114,
  feature_count_km: 113,
  groups: {},
  features: [
    { name: "brand", label: "Marka", explain: "", group: "Motorcycle", type: "categorical", options: ["Yamaha"], in_days_model: true, in_km_model: true, simple: true },
    { name: "recent_90d_km", label: "Son 90 gün km", explain: "", group: "Usage", type: "number", median: 1200, p01: 0, p99: 9000, in_days_model: true, in_km_model: true, simple: true },
  ],
};
const PREDICT = {
  prediction: { next_service_days: 24.3, next_service_km: 872.5 },
  derived: { estimated_service_date: "2026-09-21", estimated_service_odometer_km: 19072 },
  typical_model_error: { days_mae: 22, km_mae: 940, source: "x.csv" },
  input_diagnostics: { validation_errors: [], out_of_distribution: [], fields_supplied: 2, fields_imputed_days: 112, fields_imputed_km: 111 },
  model: {},
  warning: "Model developed on synthetic RideBase v1.3 data; real-fleet validation pending.",
};

function mockFetch(map: Record<string, unknown>) {
  return vi.fn(async (url: string) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const key = Object.keys(map).find((k) => path.startsWith(k));
    return {
      ok: !!key,
      status: key ? 200 : 404,
      json: async () => (key ? map[key] : { detail: "not found" }),
    } as Response;
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch({
    "/api/v1/analytics/overview": OVERVIEW,
    "/api/v1/features": FEATURES,
    "/api/v1/sample": { snapshot_id: "S1", snapshot_date: "2026-01-01", features: { brand: "Yamaha" } },
    "/api/v1/predict": PREDICT,
  }));
});

describe("dashboard smoke", () => {
  it("renders the nav with all sections and the SYNTHETIC badge", () => {
    render(<Nav active="overview" onChange={() => {}} health={null} info={null} />);
    expect(screen.getByText("GENEL BAKIŞ")).toBeInTheDocument();
    expect(screen.getByText("CANLI TAHMİN")).toBeInTheDocument();
    expect(screen.getByText(/SYNTHETIC v/)).toBeInTheDocument();
    expect(screen.getByText(/PROD VALIDATION: PENDING/)).toBeInTheDocument();
  });

  it("MetricCard shows label and value", () => {
    render(<MetricCard label="KM · R²" value="0.463" />);
    expect(screen.getByText("KM · R²")).toBeInTheDocument();
    expect(screen.getByText("0.463")).toBeInTheDocument();
  });

  it("ErrorState renders an API-offline message with retry", () => {
    const onRetry = vi.fn();
    render(<ErrorState error={new TypeError("Failed to fetch")} onRetry={onRetry} />);
    expect(screen.getByText(/API'ye ulaşılamıyor/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Tekrar dene"));
    expect(onRetry).toHaveBeenCalled();
  });

  it("Overview loads KPI cards from the analytics API", async () => {
    render(<OverviewSection info={null} />);
    expect(screen.getByText(/Servis Zamanı Tahmin Sistemi/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("KM · R²")).toBeInTheDocument(), { timeout: 2000 });
    expect(screen.getByText("0.460")).toBeInTheDocument();
  });

  it("Live prediction form submits and shows a result", async () => {
    render(<LivePredictionSection />);
    await waitFor(() => expect(screen.getByText("TAHMİN ET")).toBeInTheDocument());
    fireEvent.click(screen.getByText("TAHMİN ET"));
    await waitFor(() => expect(screen.getByText(/TAHMİNİ SONRAKİ SERVİS/)).toBeInTheDocument(), { timeout: 2000 });
    expect(screen.getByText("2026-09-21")).toBeInTheDocument();
    expect(screen.getByText(/real-fleet validation pending/)).toBeInTheDocument();
  });
});
