# RideBase Signal Ceiling / Oracle Gap Study — Preflight Gate

## Status: PASS

### 1. Environment & Git Freeze
- **Starting HEAD**: `1b06043` (matches origin/main)
- **Branch**: `main`
- **Working Tree**: Clean (excluding new study configuration)
- **Baseline Tests**: **217 / 217 passed**
  - `ridebase-ml`: 109/109 passed
  - `backend`: 83/83 passed
  - `control-center`: 25/25 passed

### 2. Verified Datasets & Baseline Models
- **V1.4 Source Tables**: Intact (`ridebase_v1_4/source_tables`)
- **V1.5 Source Tables**: Intact (`ridebase_v1_5/source_tables`)
- **V2.1 Frozen Production Model**: `ridebase-ml/models/v2_1_v1_4/champion_model.joblib` (frozen)
- **V2.2 Modeling Table**: `v2_2_modeling_table.parquet` (60 features)
- **V2.3 Modeling Table**: `v2_3_modeling_table.parquet` (95 features)
- **V1.5 Generator Event Audit**: `v1_5_generator_event_audit.parquet` (27,549 simulation events with true latent states)

### 3. Study Guardrails
- [x] V1.5 TEST set remains strictly SEALED throughout this study.
- [x] V2.1 production model, API, history store, and deploy remain completely untouched.
- [x] Oracle/latent variables are strictly partitioned for offline audit and forbidden from production contracts.
- [x] Predeclared decision criteria configured in `config/signal_ceiling_decision_thresholds.yaml`.
