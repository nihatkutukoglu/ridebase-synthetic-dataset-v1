"use client";

import { useMemo, useState } from "react";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  InfoTip,
  Loading,
  MetricCard,
  SectionHeader,
} from "@/components/ui";
import { ApiError, apiPost, useApi } from "@/lib/api";
import { nf, signed } from "@/lib/format";
import type { FeatureSpec, PredictResult } from "@/lib/types";

type FeaturesPayload = {
  count: number;
  feature_count_days: number;
  feature_count_km: number;
  groups: Record<string, FeatureSpec[]>;
  features: FeatureSpec[];
};

const GROUP_ORDER = ["Motorcycle", "Usage", "Mileage", "Service history", "Maintenance", "Other"];

export function LivePredictionSection() {
  const [mode, setMode] = useState<"simple" | "advanced">("simple");
  const { data, loading, error, reload } = useApi<FeaturesPayload>("/api/v1/features");
  const [values, setValues] = useState<Record<string, string>>({});
  const [snapshotDate, setSnapshotDate] = useState<string>("");
  const [result, setResult] = useState<PredictResult | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<ApiError | Error | null>(null);

  const shown = useMemo(() => {
    if (!data) return [];
    const list = data.features.filter((f) => f.type !== "derived");
    return mode === "simple" ? list.filter((f) => f.simple) : list;
  }, [data, mode]);

  const grouped = useMemo(() => {
    const g: Record<string, FeatureSpec[]> = {};
    shown.forEach((f) => (g[f.group] = g[f.group] || []).push(f));
    return GROUP_ORDER.filter((k) => g[k]?.length).map((k) => [k, g[k]] as const);
  }, [shown]);

  const set = (k: string, v: string) => setValues((s) => ({ ...s, [k]: v }));

  async function loadSample() {
    try {
      const s = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/api/v1/sample`).then((r) => r.json());
      const next: Record<string, string> = {};
      Object.entries(s.features as Record<string, unknown>).forEach(([k, v]) => {
        next[k] = typeof v === "boolean" ? (v ? "true" : "false") : String(v);
      });
      setValues(next);
      if (s.snapshot_date) setSnapshotDate(String(s.snapshot_date));
      setResult(null);
      setSubmitError(null);
    } catch (e) {
      setSubmitError(e as Error);
    }
  }

  async function submit() {
    setSubmitting(true);
    setSubmitError(null);
    setResult(null);
    const features: Record<string, unknown> = {};
    for (const f of data?.features ?? []) {
      const raw = values[f.name];
      if (raw === undefined || raw === "") continue;
      if (f.type === "number") features[f.name] = Number(raw);
      else if (f.type === "boolean") features[f.name] = raw === "true";
      else features[f.name] = raw;
    }
    try {
      const res = await apiPost<PredictResult>("/api/v1/predict", {
        features,
        snapshot_date: snapshotDate || null,
        strict: true,
      });
      setResult(res);
    } catch (e) {
      setSubmitError(e as ApiError);
    } finally {
      setSubmitting(false);
    }
  }

  const validationErrors =
    submitError instanceof ApiError && submitError.detail && typeof submitError.detail === "object"
      ? ((submitError.detail as { validation_errors?: string[] }).validation_errors ?? [])
      : [];

  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="CANLI TAHMİN"
        title="Bir sonraki servisi tahmin et"
        desc="Form alanları frozen model metadata'sından üretilir. Girilmeyen alanlar eğitimdeki preprocessor ile doldurulur."
      />

      {loading && <Loading />}
      {error && <ErrorState error={error} onRetry={reload} />}

      {data && (
        <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
          {/* ---------------------------------------------------- form */}
          <Card className="p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div className="inline-flex rounded-lg border border-ink-border p-0.5">
                {(["simple", "advanced"] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => setMode(m)}
                    className={`rounded-md px-3 py-1 text-xs font-semibold ${
                      mode === m ? "bg-rb-orange-soft text-rb-orange" : "text-fg-muted"
                    }`}
                  >
                    {m === "simple" ? "Basit" : "Gelişmiş"}
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={loadSample}
                  className="rounded-lg border border-ink-border px-3 py-1.5 text-xs font-semibold text-fg hover:border-rb-orange"
                >
                  Örnek veri yükle
                </button>
                <button
                  onClick={() => {
                    setValues({});
                    setResult(null);
                    setSubmitError(null);
                  }}
                  className="rounded-lg border border-ink-border px-3 py-1.5 text-xs font-semibold text-fg-muted hover:text-fg"
                >
                  Temizle
                </button>
              </div>
            </div>

            <label className="mb-4 block">
              <span className="label-tiny">Snapshot tarihi</span>
              <input
                type="date"
                value={snapshotDate}
                onChange={(e) => setSnapshotDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-ink-border bg-ink-900 px-3 py-2 text-sm text-fg [color-scheme:dark]"
              />
              <span className="mt-1 block text-[11px] text-fg-faint">
                Tahmin anının tarihi. snapshot_year/month/… ve tahmini servis tarihi bundan türetilir.
              </span>
            </label>

            <div className="space-y-4">
              {grouped.map(([group, fields]) => (
                <details key={group} open={mode === "simple" || group === "Motorcycle"} className="rounded-xl border border-ink-border bg-ink-850">
                  <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-fg">
                    {group} <span className="text-fg-faint">({fields.length})</span>
                  </summary>
                  <div className="grid gap-3 p-3 sm:grid-cols-2">
                    {fields.map((f) => (
                      <Field key={f.name} spec={f} value={values[f.name] ?? ""} onChange={(v) => set(f.name, v)} />
                    ))}
                  </div>
                </details>
              ))}
            </div>

            <button
              onClick={submit}
              disabled={submitting}
              className="mt-5 w-full rounded-xl bg-rb-orange px-4 py-2.5 text-sm font-bold text-ink-950 transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {submitting ? "Hesaplanıyor…" : "TAHMİN ET"}
            </button>

            {validationErrors.length > 0 && (
              <ul className="mt-3 space-y-1 rounded-lg border border-bad/30 bg-bad/5 p-3 text-xs text-bad">
                {validationErrors.map((e, i) => (
                  <li key={i}>• {e}</li>
                ))}
              </ul>
            )}
            {submitError && validationErrors.length === 0 && (
              <div className="mt-3">
                <ErrorState error={submitError} />
              </div>
            )}
          </Card>

          {/* ---------------------------------------------------- result */}
          <div className="space-y-4">
            {result ? (
              <ResultCard result={result} />
            ) : (
              <Card className="flex h-full min-h-[300px] items-center justify-center p-6">
                <EmptyState note="Formu doldurup TAHMİN ET'e basın. Basit modda 18 alan yeterlidir." />
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Field({
  spec,
  value,
  onChange,
}: {
  spec: FeatureSpec;
  value: string;
  onChange: (v: string) => void;
}) {
  const base =
    "mt-1 w-full rounded-lg border border-ink-border bg-ink-900 px-3 py-2 text-sm text-fg placeholder:text-fg-faint";
  return (
    <label className="block">
      <span className="flex items-center gap-1 text-xs text-fg-muted">
        {spec.label}
        {spec.explain && <InfoTip text={spec.explain} />}
      </span>
      {spec.type === "categorical" ? (
        <select value={value} onChange={(e) => onChange(e.target.value)} className={`${base} [color-scheme:dark]`}>
          <option value="">—</option>
          {(spec.options ?? []).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      ) : spec.type === "boolean" ? (
        <select value={value} onChange={(e) => onChange(e.target.value)} className={`${base} [color-scheme:dark]`}>
          <option value="">—</option>
          <option value="true">Evet</option>
          <option value="false">Hayır</option>
        </select>
      ) : (
        <input
          type="number"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={spec.median != null ? `medyan ${nf(spec.median, 1)}` : ""}
          className={base}
        />
      )}
      <span className="mt-0.5 block text-[10px] text-fg-faint">
        <code>{spec.name}</code>
        {spec.type === "number" && spec.p01 != null && spec.p99 != null && (
          <> · tipik {nf(spec.p01, 0)}–{nf(spec.p99, 0)}</>
        )}
      </span>
    </label>
  );
}

function ResultCard({ result }: { result: PredictResult }) {
  const { prediction, derived, typical_model_error, input_diagnostics } = result;
  const ood = input_diagnostics.out_of_distribution ?? [];
  return (
    <>
      <Card className="p-5">
        <div className="label-tiny text-rb-orange">TAHMİNİ SONRAKİ SERVİS</div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <div>
            <div className="metric-num text-3xl font-bold text-fg">≈ {nf(prediction.next_service_days, 0)}</div>
            <div className="text-xs text-fg-muted">gün sonra</div>
          </div>
          <div>
            <div className="metric-num text-3xl font-bold text-fg">≈ {nf(prediction.next_service_km, 0)}</div>
            <div className="text-xs text-fg-muted">km sonra</div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <MetricCard
          label="Tahmini servis tarihi"
          value={derived.estimated_service_date ?? "—"}
          accent="cyan"
          sub={derived.estimated_service_date ? "snapshot tarihi + gün" : "snapshot tarihi girilmedi"}
        />
        <MetricCard
          label="Tahmini servis km sayacı"
          value={derived.estimated_service_odometer_km != null ? `${nf(derived.estimated_service_odometer_km, 0)} km` : "—"}
          accent="cyan"
          sub={derived.estimated_service_odometer_km != null ? "güncel km + tahmini km" : "güncel km girilmedi"}
        />
      </div>

      <Card className="p-4">
        <div className="flex items-center gap-1">
          <span className="label-tiny">Tipik model hatası</span>
          <InfoTip text="Bu bir güven aralığı DEĞİLDİR. Modelin TEST setindeki ortalama mutlak hatasıdır." />
        </div>
        <div className="mt-2 flex gap-6 text-sm">
          <span className="text-fg-muted">
            DAYS MAE ≈ <b className="metric-num text-fg">{nf(typical_model_error.days_mae, 1)}</b> gün
          </span>
          <span className="text-fg-muted">
            KM MAE ≈ <b className="metric-num text-fg">{nf(typical_model_error.km_mae, 0)}</b> km
          </span>
        </div>
        <div className="mt-1 text-[10px] text-fg-faint">kaynak: {typical_model_error.source ?? "—"}</div>
      </Card>

      {ood.length > 0 && (
        <Card className="border-warn/30 p-4">
          <div className="text-xs font-semibold text-warn">Girdi eğitim aralığı dışında</div>
          <ul className="mt-1 space-y-0.5 text-[11px] text-fg-muted">
            {ood.map((o) => (
              <li key={o.field}>
                <code>{o.field}</code> = {nf(o.value, 1)} · tipik {nf(o.typical_range[0], 0)}–{nf(o.typical_range[1], 0)}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="flex flex-wrap gap-2 text-[11px] text-fg-faint">
        <Badge tone="neutral">{input_diagnostics.fields_supplied} alan girildi</Badge>
        <Badge tone="neutral">{input_diagnostics.fields_imputed_km} KM alanı dolduruldu</Badge>
        <Badge tone="neutral">{input_diagnostics.fields_imputed_days} DAYS alanı dolduruldu</Badge>
      </div>

      <p className="rounded-lg border border-warn/30 bg-warn/5 p-3 text-[11px] leading-relaxed text-fg-muted">
        {result.warning}
      </p>
    </>
  );
}
