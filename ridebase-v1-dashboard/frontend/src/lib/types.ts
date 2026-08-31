// Loose payload types — the backend normalises the notebook artifacts and every
// section tolerates {available:false}.

export interface Health {
  status: "ok" | "degraded";
  days_model_loaded: boolean;
  km_model_loaded: boolean;
  dataset_version: string;
  model_generation: string;
  leakage_guard: string;
  errors: string[];
}

export interface ModelInfo {
  days_model_name: string;
  km_model_name: string;
  days_inference_model: string;
  km_inference_model: string;
  inference_note: string | null;
  dataset_version: string;
  target_definition: string;
  split: string;
  feature_count_days: number;
  feature_count_km: number;
  days_transform: string;
  km_transform: string;
  model_generation: string;
  model_status: string;
  production_validation_status: string;
  synthetic_validation: string;
  model_config: Record<string, unknown>;
  loaded_at: string;
}

export type Row = Record<string, string | number | boolean | null>;

export interface Bands {
  available: boolean;
  source?: string;
  target?: string;
  configs?: Record<string, Record<string, number>>;
}

export interface FeatureSpec {
  name: string;
  label: string;
  explain: string;
  group: string;
  type: "number" | "categorical" | "boolean" | "derived";
  options?: string[];
  min?: number;
  max?: number;
  p01?: number;
  p99?: number;
  median?: number;
  mean?: number;
  in_days_model: boolean;
  in_km_model: boolean;
  simple: boolean;
}

export interface PredictResult {
  prediction: { next_service_days: number; next_service_km: number };
  derived: { estimated_service_date: string | null; estimated_service_odometer_km: number | null };
  typical_model_error: { days_mae: number | null; km_mae: number | null; source: string | null };
  input_diagnostics: {
    validation_errors: string[];
    out_of_distribution: { field: string; value: number; typical_range: [number, number] }[];
    fields_supplied: number;
    fields_imputed_days: number;
    fields_imputed_km: number;
  };
  model: Record<string, unknown>;
  warning: string;
}
