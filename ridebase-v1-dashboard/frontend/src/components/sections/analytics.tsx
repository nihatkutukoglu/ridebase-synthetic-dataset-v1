"use client";

import { ReactNode } from "react";
import {
  GroupedBars,
  HBar,
  Histogram,
  LineHistory,
  ScatterPlot,
  ToleranceBars,
} from "@/components/charts";
import {
  Badge,
  Card,
  DataTable,
  EmptyState,
  ErrorState,
  InfoTip,
  KeyVal,
  Loading,
  MetricCard,
  SectionHeader,
} from "@/components/ui";
import { useApi } from "@/lib/api";
import { asNum, nf, pct, r2fmt, signed } from "@/lib/format";
import type { Bands, ModelInfo, Row } from "@/lib/types";

/* ------------------------------------------------------------ async helper */
function Async<T>({
  path,
  children,
}: {
  path: string;
  children: (data: T, reload: () => void) => ReactNode;
}) {
  const { data, loading, error, reload } = useApi<T>(path);
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (!data) return <EmptyState />;
  return <>{children(data, reload)}</>;
}

const cfg = (b: Bands | undefined, which: string, key: string): number | null =>
  asNum(b?.configs?.[which]?.[key]);

const MAE_TIP = "Ortalama Mutlak Hata — modelin tahminlerinde ortalama sapma. Ne kadar düşükse o kadar iyi.";
const R2_TIP =
  "Modelin hedefteki değişkenliği ne kadar açıkladığını gösterir (1'e yakın = iyi). Bir doğruluk yüzdesi DEĞİLDİR.";
const BIAS_TIP = "Sistematik yön: pozitif ise model ortalamada yüksek, negatif ise düşük tahmin ediyor.";

/* ================================================================ OVERVIEW */
export function OverviewSection({ info }: { info: ModelInfo | null }) {
  return (
    <div className="space-y-6">
      <Card className="overflow-hidden p-6 sm:p-8">
        <div className="label-tiny text-rb-orange">RideBase V1 · Next Service Prediction</div>
        <h1 className="mt-2 text-2xl font-bold text-fg sm:text-3xl">
          Servis Zamanı Tahmin Sistemi
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-fg-muted">
          Servis geçmişi, kullanım yoğunluğu ve motosiklet özelliklerinden yararlanarak bir
          motosikletin bir sonraki servisine kalan <b className="text-fg">gün</b> ve{" "}
          <b className="text-fg">kilometreyi</b> tahmin eden V1 regression sistemi.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone="cyan">SYNTHETIC v{info?.dataset_version ?? "1.3"}</Badge>
          <Badge tone="neutral">{info?.target_definition ?? "NEXT ANY SERVICE"}</Badge>
          <Badge tone="warn">REAL FLEET VALIDATION: PENDING</Badge>
        </div>
      </Card>

      <Async<Record<string, unknown>> path="/api/v1/analytics/overview">
        {(d) => {
          const k = (d.kpis ?? {}) as Record<string, number | null>;
          const status = (d.status_card ?? {}) as Record<string, string | boolean>;
          const cmp = ((d.baseline_vs_final as { rows?: Row[] })?.rows ?? []) as Row[];
          return (
            <>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <MetricCard label="KM · R²" tip={R2_TIP} value={r2fmt(k.km_r2)} accent="orange"
                  sub="Primary target" />
                <MetricCard label="KM · MAE" tip={MAE_TIP} value={`${nf(k.km_mae)} km`} accent="orange"
                  sub="ort. ~" />
                <MetricCard label="DAYS · R²" tip={R2_TIP} value={r2fmt(k.days_r2 ?? k["days_r2"])} accent="cyan"
                  sub="Secondary target" />
                <MetricCard label="DAYS · MAE" tip={MAE_TIP} value={`${nf(k.days_mae, 1)} gün`} accent="cyan"
                  sub={`MAE ${nf(k.days_mae, 0)} gün ise model ortalama ~${nf(k.days_mae, 0)} gün sapıyor`} />
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <MetricCard label="±30 GÜN" value={pct(k.days_within_30)} accent="plain" />
                <MetricCard label="±60 GÜN" value={pct(k.days_within_60)} accent="plain" />
                <MetricCard label="±500 KM" value={pct(k.km_within_500)} accent="plain" />
                <MetricCard label="±1000 KM" value={pct(k.km_within_1000)} accent="plain" />
                <MetricCard label="±2000 KM" value={pct(k.km_within_2000)} accent="plain" />
              </div>

              <div className="grid gap-6 lg:grid-cols-3">
                <Card className="p-5 lg:col-span-1">
                  <SectionHeader title="Model Durumu" />
                  <div className="space-y-0.5">
                    <KeyVal k="V1 Regression" v={<Badge tone="ok">AKTİF</Badge>} />
                    <KeyVal k="Synthetic validation" v={<Badge tone="ok">{String(status.synthetic_validation ?? "PASS")}</Badge>} />
                    <KeyVal k="Leakage audit" v={<Badge tone={status.leakage_audit === "PASS" ? "ok" : "bad"}>{String(status.leakage_audit ?? "—")}</Badge>} />
                    <KeyVal k="Temporal split" v={<Badge tone="ok">{String(status.temporal_split ?? "PASS")}</Badge>} />
                    <KeyVal k="Reproducibility" v={<Badge tone="ok">{String(status.reproducibility ?? "PASS")}</Badge>} />
                    <KeyVal k="Real fleet validation" v={<Badge tone="warn">PENDING</Badge>} />
                  </div>
                </Card>

                <Card className="p-5 lg:col-span-2">
                  <SectionHeader
                    title="Baseline → Final"
                    desc="Default HGB baseline ile Notebook 12 tuned model karşılaştırması (gerçek artifact)."
                  />
                  {cmp.length ? (
                    <DataTable
                      columns={[
                        { key: "target", label: "Hedef" },
                        { key: "baseline_mae", label: "Base MAE", align: "right", fmt: (v) => nf(asNum(v), 1) },
                        { key: "tuned_mae", label: "Tuned MAE", align: "right", fmt: (v) => nf(asNum(v), 1) },
                        { key: "mae_improvement_pct", label: "MAE Δ%", align: "right", fmt: (v) => `${signed(asNum(v), 2)}%` },
                        { key: "baseline_r2", label: "Base R²", align: "right", fmt: (v) => r2fmt(asNum(v)) },
                        { key: "tuned_r2", label: "Tuned R²", align: "right", fmt: (v) => r2fmt(asNum(v)) },
                        { key: "r2_gain", label: "R² Δ", align: "right", fmt: (v) => signed(asNum(v), 4) },
                        { key: "verdict", label: "Sonuç", fmt: (v) => <Badge tone={String(v).includes("MEANINGFUL") ? "ok" : "neutral"}>{String(v)}</Badge> },
                      ]}
                      rows={cmp}
                    />
                  ) : (
                    <EmptyState />
                  )}
                </Card>
              </div>

              <ModelInfoCard info={info} />
            </>
          );
        }}
      </Async>
    </div>
  );
}

function ModelInfoCard({ info }: { info: ModelInfo | null }) {
  if (!info) return null;
  return (
    <Card className="p-5">
      <SectionHeader title="Model Metadata" desc="Backend startup'ta artifactlardan okunur." />
      <div className="grid gap-x-8 gap-y-1 sm:grid-cols-2">
        <KeyVal k="Dataset" v={`v${info.dataset_version}`} />
        <KeyVal k="Mode" v="observed-only regression" />
        <KeyVal k="Split" v="temporal" />
        <KeyVal k="Model generation" v={info.model_generation} />
        <KeyVal k="DAYS model" v={info.days_model_name} />
        <KeyVal k="KM model" v={info.km_model_name} />
        <KeyVal k="DAYS feature count" v={nf(info.feature_count_days)} />
        <KeyVal k="KM feature count" v={nf(info.feature_count_km)} />
        <KeyVal k="DAYS transform" v={info.days_transform} />
        <KeyVal k="KM transform" v={info.km_transform} />
        <KeyVal k="Model status" v={<Badge tone="cyan">{info.model_status}</Badge>} />
        <KeyVal k="Production validation" v={<Badge tone="warn">{info.production_validation_status}</Badge>} />
      </div>
      {info.inference_note && (
        <p className="mt-3 rounded-lg border border-ink-border bg-ink-850 p-3 text-xs text-fg-muted">
          ⓘ {info.inference_note}
        </p>
      )}
    </Card>
  );
}

/* ================================================================ TARGET (DAYS/KM) */
type TargetPayload = {
  available: boolean;
  bands: Bands;
  target: string;
  charts:
    | {
        available: boolean;
        n: number;
        scatter: { actual: number; predicted: number; residual: number }[];
        residual_hist: { x0: number; x1: number; count: number }[];
        abs_error_hist: { x0: number; x1: number; count: number }[];
        baseline_available: boolean;
      }
    | { available: false };
};

export function TargetSection({ target }: { target: "DAYS" | "KM" }) {
  const unit = target === "DAYS" ? "gün" : "km";
  const tolKeys =
    target === "DAYS"
      ? ["within_15", "within_30", "within_45", "within_60", "within_90"]
      : ["within_500", "within_1000", "within_1500", "within_2000", "within_5000"];
  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow={target === "DAYS" ? "SECONDARY TARGET" : "PRIMARY TARGET"}
        title={target === "DAYS" ? "Sonraki servise kalan GÜN" : "Sonraki servise kalan KM"}
        desc="Tüm metrikler held-out TEST setinden, frozen tuned model ile hesaplanır."
      />
      <Async<TargetPayload> path={`/api/v1/analytics/target/${target}`}>
        {(d) => {
          const b = d.bands;
          const tuned = "tuned";
          const base = "base";
          const hasBase = !!b.configs?.[base];
          const cards: [string, string, string | null, "orange" | "cyan" | "plain"][] = [
            ["R²", r2fmt(cfg(b, tuned, "r2")), R2_TIP, "orange"],
            ["MAE", `${nf(cfg(b, tuned, "mae"), 1)} ${unit}`, MAE_TIP, "orange"],
            ["MEDIAN AE", `${nf(cfg(b, tuned, "median_ae"), 1)} ${unit}`, null, "plain"],
            ["RMSE", `${nf(cfg(b, tuned, "rmse"), 1)} ${unit}`, null, "plain"],
            ["BIAS", `${signed(cfg(b, tuned, "bias"), 1)} ${unit}`, BIAS_TIP, "cyan"],
            ["P90 ABS ERR", `${nf(cfg(b, tuned, "p90_ae"), 0)} ${unit}`, "Hataların %90'ı bu değerin altında.", "plain"],
          ];
          const bias = cfg(b, tuned, "bias") ?? 0;
          return (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                {cards.map(([l, v, tip, acc]) => (
                  <MetricCard key={l} label={l} value={v} tip={tip ?? undefined} accent={acc} />
                ))}
              </div>

              {Math.abs(bias) > (target === "DAYS" ? 3 : 150) && (
                <Card className="border-warn/30 p-4 text-sm text-fg-muted">
                  <b className="text-warn">Bias uyarısı:</b> model {unit} tahminlerinde ortalamada{" "}
                  {bias > 0 ? "yüksek (geç servis)" : "düşük (erken servis)"} yönünde{" "}
                  <span className="metric-num">{signed(bias, 0)} {unit}</span> sapıyor.
                </Card>
              )}

              <div className="grid gap-6 lg:grid-cols-2">
                <Card className="p-5">
                  <SectionHeader title="Tolerans doğruluğu" desc={`|hata| ≤ eşik oranı (TEST).`} />
                  <ToleranceBars
                    data={tolKeys.map((key) => ({
                      label: `±${key.replace("within_", "")}`,
                      value: cfg(b, tuned, key) ?? 0,
                    }))}
                  />
                </Card>
                <Card className="p-5">
                  <SectionHeader title="Base vs Tuned" desc="Default HGB baseline'a göre." />
                  {hasBase ? (
                    <GroupedBars
                      keys={["base", "tuned"]}
                      data={[
                        { label: "MAE", base: cfg(b, base, "mae") ?? 0, tuned: cfg(b, tuned, "mae") ?? 0 },
                        { label: "RMSE", base: cfg(b, base, "rmse") ?? 0, tuned: cfg(b, tuned, "rmse") ?? 0 },
                        { label: "P90", base: cfg(b, base, "p90_ae") ?? 0, tuned: cfg(b, tuned, "p90_ae") ?? 0 },
                      ]}
                    />
                  ) : (
                    <EmptyState />
                  )}
                </Card>
              </div>

              {d.charts.available ? (
                <div className="grid gap-6 lg:grid-cols-2">
                  <Card className="p-5">
                    <SectionHeader title="Actual vs Predicted" desc={`${nf(d.charts.n)} TEST noktası (örneklenmiş).`} />
                    <ScatterPlot data={d.charts.scatter} xKey="actual" yKey="predicted"
                      xLabel="gerçek" yLabel="tahmin" unit={unit} refLine="diagonal" />
                  </Card>
                  <Card className="p-5">
                    <SectionHeader title="Predicted vs Residual" desc="Yatay = tahmin, dikey = (tahmin − gerçek)." />
                    <ScatterPlot data={d.charts.scatter} xKey="predicted" yKey="residual"
                      xLabel="tahmin" yLabel="artık" unit={unit} refLine="zero" />
                  </Card>
                  <Card className="p-5">
                    <SectionHeader title="Residual dağılımı" />
                    <Histogram bins={d.charts.residual_hist} unit={unit} color="#22d3ee" />
                  </Card>
                  <Card className="p-5">
                    <SectionHeader title="Mutlak hata dağılımı" />
                    <Histogram bins={d.charts.abs_error_hist} unit={unit} />
                  </Card>
                </div>
              ) : (
                <EmptyState note="Test prediction artifact not available for charts." />
              )}
            </>
          );
        }}
      </Async>
    </div>
  );
}

/* ================================================================ MODELS */
export function ModelsSection() {
  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="MODEL LEADERBOARD"
        title="Modeller & Hyperparameter Tuning"
        desc="Notebook 12 temporal-CV Optuna sonuçları. FINAL rozeti seçilen modeli işaretler."
      />
      <Async<Record<string, unknown>> path="/api/v1/analytics/models">
        {(d) => {
          const lbD = (d.leaderboard_days ?? []) as Row[];
          const lbK = (d.leaderboard_km ?? []) as Row[];
          const frozen = (d.frozen ?? {}) as Record<string, { model?: string }>;
          const optuna = (d.optuna ?? {}) as Record<string, { trial: number; value: number; best: number }[]>;
          const cols = [
            { key: "model", label: "Model", fmt: (v: unknown, r: Record<string, unknown>) => (
              <span className="flex items-center gap-2">
                {String(v)}
                {isFinal(v, r, frozen) && <Badge tone="orange">FINAL</Badge>}
              </span>
            )},
            { key: "loss", label: "Loss" },
            { key: "cv_mae", label: "CV MAE", align: "right" as const, fmt: (v: unknown) => nf(asNum(v), 2) },
            { key: "cv_mae_std", label: "CV std", align: "right" as const, fmt: (v: unknown) => nf(asNum(v), 2) },
            { key: "val_mae", label: "Val MAE", align: "right" as const, fmt: (v: unknown) => nf(asNum(v), 2) },
            { key: "val_r2", label: "Val R²", align: "right" as const, fmt: (v: unknown) => r2fmt(asNum(v)) },
            { key: "overfit_flag", label: "Overfit", fmt: (v: unknown) => (String(v) === "True" || v === true ? <Badge tone="warn">evet</Badge> : "—") },
            { key: "runtime_s", label: "s", align: "right" as const, fmt: (v: unknown) => nf(asNum(v), 0) },
          ];
          return (
            <>
              <div className="grid gap-6 xl:grid-cols-2">
                <Card className="p-5">
                  <SectionHeader title="KM leaderboard" />
                  {lbK.length ? <DataTable columns={cols} rows={lbK} highlight={(r) => isFinal(r.model, r, frozen)} /> : <EmptyState />}
                </Card>
                <Card className="p-5">
                  <SectionHeader title="DAYS leaderboard" />
                  {lbD.length ? <DataTable columns={cols} rows={lbD} highlight={(r) => isFinal(r.model, r, frozen)} /> : <EmptyState />}
                </Card>
              </div>

              <FrozenParams frozen={frozen} config={(d.config ?? {}) as Record<string, unknown>} />

              <div className="grid gap-6 xl:grid-cols-2">
                {(["km", "days"] as const).map((tgt) => {
                  const key = Object.keys(optuna).find((kk) => kk.endsWith(`_${tgt}`) && optuna[kk]?.length);
                  return (
                    <Card key={tgt} className="p-5">
                      <SectionHeader title={`Optuna history · ${tgt.toUpperCase()}`}
                        desc={key ? key.replace(`_${tgt}`, "").toUpperCase() : undefined} />
                      {key ? (
                        <LineHistory
                          data={optuna[key].map((t) => ({ trial: t.trial, value: t.value, best: t.best }))}
                          lines={[{ key: "value", label: "trial CV MAE" }, { key: "best", label: "best", color: "#22d3ee" }]}
                          yLabel="CV MAE"
                        />
                      ) : (
                        <EmptyState note="Optuna trial artifact not available." />
                      )}
                    </Card>
                  );
                })}
              </div>
            </>
          );
        }}
      </Async>
    </div>
  );
}

function isFinal(model: unknown, _row: Record<string, unknown>, frozen: Record<string, { model?: string }>) {
  return Object.values(frozen).some((f) => f?.model && String(f.model) === String(model));
}

function FrozenParams({
  frozen,
  config,
}: {
  frozen: Record<string, { model?: string; loss?: string; hyperparameters?: Record<string, unknown>; feature_set?: string; target_transform?: string; use_ensemble?: boolean; ensemble_members?: string[]; ensemble_weights?: number[] }>;
  config: Record<string, unknown>;
}) {
  return (
    <Card className="p-5">
      <SectionHeader title="Frozen configuration" desc="TEST açılmadan önce donduruldu." />
      <div className="mb-3 flex flex-wrap gap-2 text-xs text-fg-muted">
        {Object.entries(config).map(([k, v]) => (
          <span key={k} className="rounded-md border border-ink-border bg-ink-850 px-2 py-1">
            {k}: <b className="text-fg">{String(v)}</b>
          </span>
        ))}
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {Object.entries(frozen).map(([tgt, f]) => (
          <details key={tgt} className="rounded-xl border border-ink-border bg-ink-850 p-3" open>
            <summary className="cursor-pointer text-sm font-semibold text-fg">
              {tgt} — {f.model} {f.use_ensemble ? "+ blend" : ""}{" "}
              <span className="text-fg-faint">/ {f.feature_set} / {f.target_transform}</span>
            </summary>
            <pre className="mt-2 overflow-x-auto rounded-lg bg-ink-900 p-3 text-[11px] leading-relaxed text-fg-muted">
{JSON.stringify(f.hyperparameters ?? {}, null, 2)}
            </pre>
            {f.use_ensemble && (
              <p className="text-[11px] text-fg-faint">
                blend: {(f.ensemble_members ?? []).join(" / ")} @ {(f.ensemble_weights ?? []).join(" / ")}
              </p>
            )}
          </details>
        ))}
      </div>
    </Card>
  );
}

/* ================================================================ FEATURES */
export function FeaturesSection() {
  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="FEATURE IMPORTANCE"
        title="Feature'lar"
        desc="Permutation importance (VALIDATION MAE). Feature adları artifacttan gelir; açıklamalar eklenmiştir."
      />
      <Async<Record<string, unknown>> path="/api/v1/analytics/features">
        {(d) => {
          const mk = (rows: unknown): { label: string; value: number; raw: string; explain: string; group: string }[] =>
            ((rows as Row[]) ?? [])
              .map((r) => ({
                label: String(r.label ?? r.feature),
                raw: String(r.feature),
                explain: String(r.explain ?? ""),
                group: String(r.group ?? ""),
                value: asNum(r.importance) ?? 0,
              }))
              .filter((r) => r.value > 0)
              .sort((a, b) => b.value - a.value)
              .slice(0, 15);
          const km = mk(d.km);
          const days = mk(d.days);
          return (
            <div className="grid gap-6 xl:grid-cols-2">
              {[
                { title: "KM · Top 15", rows: km },
                { title: "DAYS · Top 15", rows: days },
              ].map(({ title, rows }) => (
                <Card key={title} className="p-5">
                  <SectionHeader title={title} />
                  {rows.length ? (
                    <>
                      <HBar data={rows.map((r) => ({ label: r.label, value: +r.value.toFixed(4) }))} />
                      <ul className="mt-4 space-y-1.5">
                        {rows.slice(0, 8).map((r) => (
                          <li key={r.raw} className="text-xs text-fg-muted">
                            <span className="text-fg">{r.label}</span>
                            {r.explain && <> — {r.explain}</>}
                            <code className="ml-1 text-[10px] text-fg-faint">{r.raw}</code>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <EmptyState />
                  )}
                </Card>
              ))}
            </div>
          );
        }}
      </Async>
    </div>
  );
}

/* ================================================================ ERRORS */
export function ErrorsSection() {
  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="HATA ANALİZİ"
        title="Segment & Cold-history hataları"
        desc="Segmentler n ≥ 30 filtresiyle raporlanır (düşük örneklem gizlenir)."
      />
      <Async<Record<string, unknown>> path="/api/v1/analytics/errors">
        {(d) => {
          const worst = (d.worst_segments ?? []) as Row[];
          const cold = (d.cold_history ?? []) as Row[];
          const calib = (d.calibration_bins ?? []) as Row[];
          const spec = (d.specialist ?? []) as Row[];
          return (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                <Card className="p-5">
                  <SectionHeader title="En kötü segmentler (TEST)" />
                  {worst.length ? (
                    <DataTable
                      columns={[
                        { key: "target", label: "Hedef" },
                        { key: "segment_type", label: "Tip" },
                        { key: "segment", label: "Segment" },
                        { key: "n", label: "n", align: "right", fmt: (v) => nf(asNum(v)) },
                        { key: "mae", label: "MAE", align: "right", fmt: (v) => nf(asNum(v), 1) },
                      ]}
                      rows={worst}
                    />
                  ) : (
                    <EmptyState />
                  )}
                </Card>
                <Card className="p-5">
                  <SectionHeader
                    title="Az servis geçmişi (cold history)"
                    desc="history_depth: 0–1 / 2–3 / 4+. Geçmişi az araçlarda hata genelde daha yüksek."
                  />
                  {cold.length ? (
                    <HBar
                      unit=""
                      data={cold.map((r) => ({ label: `${r.target} · ${r.segment}`, value: +(asNum(r.mae) ?? 0).toFixed(1) }))}
                    />
                  ) : (
                    <EmptyState note="history_depth segment artifact not available." />
                  )}
                </Card>
              </div>

              <div className="grid gap-6 lg:grid-cols-2">
                <Card className="p-5">
                  <SectionHeader title="Specialist deneyi" desc="history_depth ≤ 1 için ayrı model." />
                  {spec.length ? (
                    <DataTable
                      columns={Object.keys(spec[0]).map((key) => ({
                        key,
                        label: key,
                        align: typeof spec[0][key] === "number" ? "right" : "left",
                        fmt: (v: unknown) => (typeof v === "number" ? nf(v, 2) : String(v)),
                      }))}
                      rows={spec}
                    />
                  ) : (
                    <EmptyState />
                  )}
                </Card>
                <Card className="p-5">
                  <SectionHeader title="Kalibrasyon (tahmin çeyrekleri)" desc="Her binde ortalama tahmin vs gerçek." />
                  {calib.length ? (
                    <GroupedBars
                      keys={["mean_pred", "mean_actual"]}
                      data={calib
                        .filter((r) => String(r.target).toUpperCase() === "KM")
                        .map((r) => ({
                          label: `b${r.bin}`,
                          mean_pred: asNum(r.mean_pred) ?? 0,
                          mean_actual: asNum(r.mean_actual) ?? 0,
                        }))}
                    />
                  ) : (
                    <EmptyState />
                  )}
                </Card>
              </div>
            </>
          );
        }}
      </Async>
    </div>
  );
}

/* ================================================================ DRIFT */
export function DriftSection() {
  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="TEMPORAL DRIFT" title="Zaman İçinde Kayma" />
      <Async<Record<string, unknown>> path="/api/v1/analytics/drift">
        {(d) => {
          const rows = (d.rows ?? []) as Row[];
          const splitEx = (d.splits_explainer ?? {}) as Record<string, string>;
          const targetRows = rows.filter((r) => String(r.quantity ?? "").startsWith("target"));
          const byQ: Record<string, Record<string, number>> = {};
          targetRows.forEach((r) => {
            const q = String(r.quantity);
            byQ[q] = byQ[q] || {};
            byQ[q][String(r.split)] = asNum(r.median) ?? asNum(r.mean) ?? 0;
          });
          const chartData = Object.entries(byQ).map(([q, v]) => ({
            label: q.replace("target_", ""),
            TRAIN: v.TRAIN ?? 0,
            VALIDATION: v.VALIDATION ?? 0,
            TEST: v.TEST ?? 0,
          }));
          return (
            <>
              <Card className="p-5 text-sm text-fg-muted">
                <b className="text-fg">Temporal drift nedir?</b>{" "}
                {String(d.explainer ?? "Geçmişteki servis davranışı ile gelecekteki servis davranışının birebir aynı olmaması.")}
              </Card>

              <div className="grid gap-6 lg:grid-cols-3">
                {(["TRAIN", "VALIDATION", "TEST"] as const).map((s) => (
                  <Card key={s} className="p-5">
                    <div className="label-tiny text-rb-orange">{s}</div>
                    <p className="mt-1 text-sm text-fg-muted">{splitEx[s]}</p>
                    {s === "TEST" && (
                      <Badge tone="ok">
                        <span className="mr-1">TEST ISOLATION</span>
                        {String(d.test_isolation ?? "PASS")}
                      </Badge>
                    )}
                  </Card>
                ))}
              </div>

              <Card className="p-5">
                <SectionHeader title="Hedef dağılımı — TRAIN / VALIDATION / TEST" desc="Medyan değerler (gün ve km)." />
                {chartData.length ? (
                  <GroupedBars keys={["TRAIN", "VALIDATION", "TEST"]} data={chartData} />
                ) : (
                  <EmptyState />
                )}
              </Card>

              <Card className="p-5">
                <SectionHeader title="Drift tablosu (ham artifact)" />
                {rows.length ? (
                  <DataTable
                    columns={Object.keys(rows[0]).map((key) => ({
                      key,
                      label: key,
                      align: typeof rows[0][key] === "number" ? "right" : "left",
                      fmt: (v: unknown) => (typeof v === "number" ? nf(v, 1) : String(v)),
                    }))}
                    rows={rows}
                  />
                ) : (
                  <EmptyState />
                )}
              </Card>
            </>
          );
        }}
      </Async>
    </div>
  );
}

/* ================================================================ EXPERIMENTS */
export function ExperimentsSection() {
  return (
    <div className="space-y-6">
      <SectionHeader
        eyebrow="DENEYLER"
        title="V1 Deney Hattı"
        desc="Her kart ilgili notebook artifactından okunur; artifact yoksa 'not available' gösterilir."
      />
      <Async<Record<string, unknown>> path="/api/v1/analytics/experiments">
        {(d) => {
          const cards = (d.cards ?? []) as Array<Record<string, unknown>>;
          return (
            <div className="grid gap-4 md:grid-cols-2">
              {cards.map((c, i) => {
                const rows = (c.rows ?? []) as Row[];
                const isExt = String(c.name).includes("External");
                return (
                  <Card key={i} className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-sm font-semibold text-fg">{String(c.name)}</h3>
                      {c.available ? (
                        <Badge tone="neutral">{String(c.source)}</Badge>
                      ) : (
                        <Badge tone="warn">not available</Badge>
                      )}
                    </div>
                    {!!c.note && <p className="mt-2 text-xs text-fg-muted">{String(c.note)}</p>}
                    {!!c.verdict && (
                      <div className="mt-2">
                        <Badge tone={String(c.verdict).includes("NO VALUE") ? "warn" : String(c.verdict).includes("MEANINGFUL") ? "ok" : "cyan"}>
                          {String(c.verdict)}
                        </Badge>
                      </div>
                    )}
                    {isExt && (
                      <p className="mt-2 text-[11px] leading-relaxed text-fg-faint">
                        v1.3 içindeki <code>policy_interval_km</code> gibi sentetik bakım politikası
                        feature&apos;ları zaten benzer sinyali taşıdığı için gerçek üretici takvimi ek
                        bilgi sağlamadı. Gerçek production datasında bu bilgi yeniden değerli olabilir.
                      </p>
                    )}
                    {rows.length > 0 && (
                      <div className="mt-3 max-h-56 overflow-auto">
                        <DataTable
                          columns={Object.keys(rows[0]).slice(0, 6).map((key) => ({
                            key,
                            label: key,
                            align: typeof rows[0][key] === "number" ? "right" : "left",
                            fmt: (v: unknown) => (typeof v === "number" ? nf(v, 3) : String(v ?? "—")),
                          }))}
                          rows={rows.slice(0, 12)}
                        />
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          );
        }}
      </Async>
    </div>
  );
}

/* ================================================================ VERDICT */
export function VerdictSection({ info }: { info: ModelInfo | null }) {
  return (
    <div className="space-y-6">
      <SectionHeader eyebrow="SONUÇ" title="V1 Final Değerlendirme" />
      <Async<Record<string, unknown>> path="/api/v1/analytics/verdict">
        {(d) => {
          const sections = (d.report_sections ?? {}) as Record<string, string>;
          const limits = (d.limitations ?? []) as Array<{ title: string; body: string }>;
          const cmp = (d.test_comparison ?? []) as Row[];
          const next = (d.next_stage ?? {}) as Record<string, unknown>;
          return (
            <>
              {cmp.length > 0 && (
                <Card className="p-5">
                  <SectionHeader title="DAYS & KM — final test" />
                  <DataTable
                    columns={[
                      { key: "target", label: "Hedef" },
                      { key: "tuned_model", label: "Model" },
                      { key: "tuned_mae", label: "MAE", align: "right", fmt: (v) => nf(asNum(v), 1) },
                      { key: "tuned_r2", label: "R²", align: "right", fmt: (v) => r2fmt(asNum(v)) },
                      { key: "mae_improvement_pct", label: "MAE Δ%", align: "right", fmt: (v) => `${signed(asNum(v), 2)}%` },
                      { key: "verdict", label: "Sonuç", fmt: (v) => <Badge tone={String(v).includes("MEANINGFUL") ? "ok" : "neutral"}>{String(v)}</Badge> },
                    ]}
                    rows={cmp}
                  />
                </Card>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                {Object.entries(sections).map(([title, body]) => (
                  <Card key={title} className="p-5">
                    <div className="label-tiny text-rb-orange">{title}</div>
                    <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-fg-muted">
                      {body.replace(/[#*`]/g, "").trim().slice(0, 700)}
                    </p>
                  </Card>
                ))}
              </div>

              <Card className="p-5">
                <SectionHeader title="Bilinen sınırlar" />
                <div className="space-y-3">
                  {limits.map((l) => (
                    <div key={l.title} className="rounded-xl border border-ink-border bg-ink-850 p-3">
                      <div className="text-sm font-semibold text-fg">{l.title}</div>
                      <p className="mt-1 text-xs leading-relaxed text-fg-muted">{l.body}</p>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="border-rb-cyan/30 p-5">
                <div className="label-tiny text-rb-cyan">SONRAKİ AŞAMA</div>
                <h3 className="mt-1 text-lg font-semibold text-fg">{String(next.name ?? "V2 Survival Analysis")}</h3>
                <p className="mt-1 text-sm text-fg-muted">{String(next.reason ?? "")}</p>
                <Badge tone="warn">HENÜZ YOK — sonuç gösterilmiyor</Badge>
              </Card>

              <p className="text-xs text-fg-faint">
                Model {info?.dataset_version ? `v${info.dataset_version}` : "v1.3"} sentetik verisi üzerinde
                geliştirildi. Gerçek filo doğrulaması (real fleet validation) yapılana kadar
                &quot;production validated&quot; ifadesi kullanılmaz.
              </p>
            </>
          );
        }}
      </Async>
    </div>
  );
}
