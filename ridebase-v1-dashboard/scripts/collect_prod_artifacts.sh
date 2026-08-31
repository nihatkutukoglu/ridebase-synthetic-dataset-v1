#!/usr/bin/env bash
# Curate the inference-only artifact subset (~50 MB) into backend/artifacts/.
# Excludes the ~5 GB of AutoML experiment models that inference never touches.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"          # ridebase-v1-dashboard/
ml="$(cd "$here/../ridebase-ml" && pwd)"
ds="$(cd "$here/../ridebase_v1_3/derived_outputs" && pwd)"
dst="$here/backend/artifacts"

rm -rf "$dst"
mkdir -p "$dst/models" "$dst/reports/tables" "$dst/reports/figures" "$dst/outputs" "$dst/dataset"

# models: frozen V1 + V2 bundle files only (skip */v1_automl */v1_3_automl)
rsync -a --prune-empty-dirs \
  --include='*/' \
  --include='v0_*' --include='v1_final_*' --include='v1_ext_*' --include='v1_3_final_*' \
  --include='v2_advanced_*' --include='v2_feature_catalog.json' \
  --include='v2_production_bundle_manifest.json' --include='v2_coxnet_model.joblib' \
  --include='v2_xgb_cox_model.json' \
  --exclude='*' \
  "$ml/models/" "$dst/models/"

cp -R "$ml/reports/tables/." "$dst/reports/tables/"
cp "$ml"/reports/*.md "$dst/reports/" 2>/dev/null || true
# V2 calibration figures the Control Center links to (small PNGs)
cp -R "$ml/reports/figures/v2_survival_advanced/." "$dst/reports/figures/v2_survival_advanced/" 2>/dev/null || true
cp "$ml"/outputs/v1_final_tuning_test_predictions.parquet "$dst/outputs/" 2>/dev/null || true
cp "$ml"/outputs/v2_advanced_test_predictions.parquet "$dst/outputs/" 2>/dev/null || true
cp "$ds/ml_maintenance_snapshots.parquet" "$ds/dataset_metadata.json" "$dst/dataset/" 2>/dev/null || true

du -sh "$dst"
echo "OK  -> $dst  (commit it, or upload to the Render /artifacts disk)"
