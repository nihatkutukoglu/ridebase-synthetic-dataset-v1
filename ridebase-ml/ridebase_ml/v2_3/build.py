"""Build V2.3 observable history features without reading outcome columns."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .features import FEATURE_COLUMNS, GROUPS, NEW_FEATURES, contract_rows


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def _cv(values: np.ndarray) -> float:
    if len(values) < 2 or abs(float(np.mean(values))) < 1e-12:
        return 0.0
    return float(np.std(values, ddof=0) / abs(np.mean(values)))


def _slope(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(values), dtype=float), values.astype(float), 1)[0])


def _one(landmark: np.datetime64, appt: pd.DataFrame, svc: pd.DataFrame, mil: pd.DataFrame) -> dict[str, float]:
    """Independent, readable single-landmark reference implementation."""
    lm = pd.Timestamp(landmark).normalize()
    a = appt.loc[pd.to_datetime(appt.created_at) <= lm].copy()
    a["created_at"] = pd.to_datetime(a.created_at).dt.normalize()
    a["scheduled_at"] = pd.to_datetime(a.scheduled_at).dt.normalize()
    prior_a = a.loc[a.scheduled_at <= lm].sort_values("scheduled_at")
    n = len(prior_a)
    ns = prior_a.status.eq("NO_SHOW")
    ca = prior_a.status.eq("CANCELLED")
    ok = prior_a.status.eq("CONVERTED_TO_SERVICE")
    rebooked = []
    for when in prior_a.loc[ns, "scheduled_at"]:
        rebooked.append(bool(((a.created_at > when) & (a.created_at <= lm)).any()))

    s = svc.copy()
    s["delivered_at"] = pd.to_datetime(s.delivered_at, errors="coerce").dt.normalize()
    s = s.loc[s.status.eq("DELIVERED") & s.delivered_at.notna() & (s.delivered_at <= lm)].sort_values("delivered_at")
    delays = pd.to_numeric(s.service_delay_days, errors="coerce").fillna(0).to_numpy(float)
    dates = s.delivered_at.to_numpy(dtype="datetime64[D]")
    gaps = np.diff(dates).astype("timedelta64[D]").astype(float) if len(dates) > 1 else np.array([])
    odo = pd.to_numeric(s.odometer_km, errors="coerce").to_numpy(float)
    kmg = np.diff(odo); kmg = kmg[np.isfinite(kmg) & (kmg > 0)]
    overdue = ((pd.to_numeric(s.maintenance_overdue_days_pre_service, errors="coerce").fillna(0) > 0) |
               (pd.to_numeric(s.maintenance_overdue_km_pre_service, errors="coerce").fillna(0) > 0))
    ages = (lm.to_datetime64().astype("datetime64[D]") - dates).astype("timedelta64[D]").astype(float) if len(dates) else np.array([])
    weights = np.exp(-ages / 365.0) if len(ages) else np.array([])
    workshops = s.workshop_id.astype(str).to_numpy()
    streak = 0
    if len(workshops):
        streak = next((i for i, x in enumerate(workshops[::-1]) if x != workshops[-1]), len(workshops))

    m = mil.copy()
    m["period_end_date"] = pd.to_datetime(m.period_end_date).dt.normalize()
    m = m.loc[m.period_end_date <= lm].sort_values("period_end_date")
    km = pd.to_numeric(m.km_added, errors="coerce").fillna(0)
    recent30 = float(km.loc[m.period_end_date >= lm - pd.Timedelta(days=29)].sum())
    recent180 = float(km.loc[m.period_end_date >= lm - pd.Timedelta(days=179)].sum())
    br = s.loc[s.is_breakdown.eq(1) | s.service_type_code.eq("BREAKDOWN")]
    rep = s.loc[s.service_type_code.eq("REPAIR")]
    interactions = pd.concat([a.created_at, s.delivered_at], ignore_index=True).dropna()
    recent_ns = prior_a.loc[ns & (prior_a.scheduled_at >= lm - pd.Timedelta(days=179)), "scheduled_at"]
    unrebooked = any(not bool(((a.created_at > x) & (a.created_at <= lm)).any()) for x in recent_ns)
    return {
        "appointments_180d": float(((prior_a.scheduled_at >= lm-pd.Timedelta(days=179))).sum()),
        "attended_appointment_count": float(ok.sum()), "no_show_rate": float(ns.sum()/n) if n else 0.,
        "cancellation_rate": float(ca.sum()/n) if n else 0., "successful_appointment_rate": float(ok.sum()/n) if n else 0.,
        "rebook_after_no_show_rate": float(np.mean(rebooked)) if rebooked else 0.,
        "days_since_last_appointment": float((lm-prior_a.scheduled_at.max()).days) if n else np.nan,
        "known_open_appointment_count": float((a.scheduled_at > lm).sum()), "recent_no_show_without_rebook": float(unrebooked),
        "overdue_service_share": float(overdue.mean()) if len(s) else 0.,
        "prior_service_delay_median": float(np.median(delays)) if len(delays) else 0.,
        "prior_service_delay_p90": float(np.quantile(delays,.9)) if len(delays) else 0.,
        "last3_service_delay_trend": _slope(delays[-3:]), "interservice_days_cv": _cv(gaps), "interservice_km_cv": _cv(kmg),
        "recency_weighted_adherence_score": float(np.average(delays<=0,weights=weights)) if len(weights) else .5,
        "service_gap_acceleration": float(gaps[-1]/np.mean(gaps[:-1])-1) if len(gaps)>=2 and np.mean(gaps[:-1])>0 else 0.,
        "days_since_last_any_interaction": float((lm-interactions.max()).days) if len(interactions) else np.nan,
        "interaction_count_90d": float((interactions>=lm-pd.Timedelta(days=89)).sum()),
        "interaction_count_180d": float((interactions>=lm-pd.Timedelta(days=179)).sum()),
        "appointment_frequency_365d": float((a.created_at>=lm-pd.Timedelta(days=364)).sum()),
        "distinct_workshops_before_landmark": float(len(set(workshops))),
        "dominant_workshop_share": float(pd.Series(workshops).value_counts(normalize=True).max()) if len(workshops) else 0.,
        "same_workshop_streak": float(streak), "recent_30d_km": recent30, "recent_180d_km": recent180,
        "usage_velocity_ratio_30_vs_180": float((recent30/30)/(recent180/180)) if recent180>0 else 0.,
        "usage_volatility_6m": _cv(km.to_numpy(float)[-6:]),
        "odometer_observation_recency_days": float((lm-m.period_end_date.max()).days) if len(m) else np.nan,
        "km_growth_slope_6m": _slope(km.to_numpy(float)[-6:]),
        "breakdown_count_90d": float((br.delivered_at>=lm-pd.Timedelta(days=89)).sum()),
        "repair_count_90d": float((rep.delivered_at>=lm-pd.Timedelta(days=89)).sum()),
        "safety_critical_repair_recent": float(((s.delivered_at>=lm-pd.Timedelta(days=179)) & s.failure_severity.isin(["HIGH","CRITICAL"])).any()),
        "days_since_last_breakdown": float((lm-br.delivered_at.max()).days) if len(br) else np.nan,
        "repeated_breakdown_flag": float((br.delivered_at>=lm-pd.Timedelta(days=364)).sum()>=2),
    }


def _group_matrix(landmarks: pd.Series, appt: pd.DataFrame, svc: pd.DataFrame, mil: pd.DataFrame) -> dict[str, np.ndarray]:
    """Fast numpy implementation used for the full table (separate from `_one`)."""
    lms = pd.to_datetime(landmarks).to_numpy(dtype="datetime64[D]")
    result = {name: np.full(len(lms), np.nan) for name in NEW_FEATURES}
    a_created = appt.created_at.to_numpy(dtype="datetime64[D]")
    a_sched = appt.scheduled_at.to_numpy(dtype="datetime64[D]")
    a_status = appt.status.astype(str).to_numpy()
    completed = svc.loc[svc.status.eq("DELIVERED") & svc.delivered_at.notna()].sort_values("delivered_at")
    s_dates = completed.delivered_at.to_numpy(dtype="datetime64[D]")
    s_delay = pd.to_numeric(completed.service_delay_days, errors="coerce").fillna(0).to_numpy(float)
    s_odo = pd.to_numeric(completed.odometer_km, errors="coerce").to_numpy(float)
    s_ws = completed.workshop_id.astype(str).to_numpy()
    s_type = completed.service_type_code.astype(str).to_numpy()
    s_break = completed.is_breakdown.fillna(0).to_numpy(float).astype(bool) | (s_type == "BREAKDOWN")
    s_sev = completed.failure_severity.astype(str).to_numpy()
    s_overdue = ((pd.to_numeric(completed.maintenance_overdue_days_pre_service, errors="coerce").fillna(0).to_numpy(float) > 0) |
                 (pd.to_numeric(completed.maintenance_overdue_km_pre_service, errors="coerce").fillna(0).to_numpy(float) > 0))
    ordered_m = mil.sort_values("period_end_date")
    m_dates = ordered_m.period_end_date.to_numpy(dtype="datetime64[D]")
    m_km = pd.to_numeric(ordered_m.km_added, errors="coerce").fillna(0).to_numpy(float)
    day = np.timedelta64(1, "D")
    for i, lm in enumerate(lms):
        ak = (a_created <= lm)
        ap = ak & (a_sched <= lm)
        sched = a_sched[ap]; status = a_status[ap]; n = len(sched)
        ns_dates = sched[status == "NO_SHOW"]
        max_created = np.max(a_created[ak]) if np.any(ak) else np.datetime64("NaT")
        result["appointments_180d"][i] = np.sum(ap & (a_sched >= lm-179*day))
        result["attended_appointment_count"][i] = np.sum(status == "CONVERTED_TO_SERVICE")
        result["no_show_rate"][i] = np.sum(status == "NO_SHOW")/n if n else 0.
        result["cancellation_rate"][i] = np.sum(status == "CANCELLED")/n if n else 0.
        result["successful_appointment_rate"][i] = np.sum(status == "CONVERTED_TO_SERVICE")/n if n else 0.
        result["rebook_after_no_show_rate"][i] = np.mean(max_created > ns_dates) if len(ns_dates) else 0.
        result["days_since_last_appointment"][i] = float((lm-np.max(sched))/day) if n else np.nan
        result["known_open_appointment_count"][i] = np.sum(ak & (a_sched > lm))
        recent_ns = ns_dates[ns_dates >= lm-179*day]
        result["recent_no_show_without_rebook"][i] = float(np.any(max_created <= recent_ns)) if len(recent_ns) else 0.

        sn = int(np.searchsorted(s_dates, lm, side="right")); dates=s_dates[:sn]; delays=s_delay[:sn]
        gaps=np.diff(dates).astype("timedelta64[D]").astype(float) if sn>1 else np.array([])
        kmg=np.diff(s_odo[:sn]); kmg=kmg[np.isfinite(kmg)&(kmg>0)]
        ages=(lm-dates).astype("timedelta64[D]").astype(float) if sn else np.array([]); weights=np.exp(-ages/365.) if sn else np.array([])
        result["overdue_service_share"][i]=float(np.mean(s_overdue[:sn])) if sn else 0.
        result["prior_service_delay_median"][i]=float(np.median(delays)) if sn else 0.
        result["prior_service_delay_p90"][i]=float(np.quantile(delays,.9)) if sn else 0.
        result["last3_service_delay_trend"][i]=_slope(delays[-3:])
        result["interservice_days_cv"][i]=_cv(gaps); result["interservice_km_cv"][i]=_cv(kmg)
        result["recency_weighted_adherence_score"][i]=float(np.average(delays<=0,weights=weights)) if sn else .5
        result["service_gap_acceleration"][i]=float(gaps[-1]/np.mean(gaps[:-1])-1) if len(gaps)>=2 and np.mean(gaps[:-1])>0 else 0.
        prior_created=a_created[ak]; interactions=np.concatenate([prior_created,dates]) if sn or len(prior_created) else np.array([],dtype="datetime64[D]")
        result["days_since_last_any_interaction"][i]=float((lm-np.max(interactions))/day) if len(interactions) else np.nan
        result["interaction_count_90d"][i]=np.sum(interactions>=lm-89*day); result["interaction_count_180d"][i]=np.sum(interactions>=lm-179*day)
        result["appointment_frequency_365d"][i]=np.sum(prior_created>=lm-364*day)
        ws=s_ws[:sn]; result["distinct_workshops_before_landmark"][i]=len(set(ws))
        if sn:
            _,counts=np.unique(ws,return_counts=True); result["dominant_workshop_share"][i]=float(np.max(counts)/sn)
            streak=1
            for j in range(sn-2,-1,-1):
                if ws[j]!=ws[-1]: break
                streak+=1
            result["same_workshop_streak"][i]=streak
        else: result["dominant_workshop_share"][i]=0.; result["same_workshop_streak"][i]=0.

        mn=int(np.searchsorted(m_dates,lm,side="right")); md=m_dates[:mn]; mk=m_km[:mn]
        r30=float(np.sum(mk[md>=lm-29*day])); r180=float(np.sum(mk[md>=lm-179*day]))
        result["recent_30d_km"][i]=r30; result["recent_180d_km"][i]=r180
        result["usage_velocity_ratio_30_vs_180"][i]=(r30/30)/(r180/180) if r180>0 else 0.
        result["usage_volatility_6m"][i]=_cv(mk[-6:]); result["km_growth_slope_6m"][i]=_slope(mk[-6:])
        result["odometer_observation_recency_days"][i]=float((lm-md[-1])/day) if mn else np.nan
        br=s_break[:sn]; recent90=dates>=lm-89*day; recent180=dates>=lm-179*day; recent365=dates>=lm-364*day
        result["breakdown_count_90d"][i]=np.sum(br&recent90); result["repair_count_90d"][i]=np.sum((s_type[:sn]=="REPAIR")&recent90)
        result["safety_critical_repair_recent"][i]=float(np.any(np.isin(s_sev[:sn],["HIGH","CRITICAL"])&recent180))
        result["days_since_last_breakdown"][i]=float((lm-dates[br][-1])/day) if np.any(br) else np.nan
        result["repeated_breakdown_flag"][i]=float(np.sum(br&recent365)>=2)
    return result


def build(repo_root: Path) -> dict:
    root = Path(repo_root).resolve(); ml = root / "ridebase-ml"
    source = root / "ridebase_v1_5/source_tables"
    base = pd.read_parquet(ml / "derived_outputs/v2_2_v1_5/v2_2_modeling_table.parquet")
    appt = pd.read_csv(source / "appointments.csv", low_memory=False)
    svc = pd.read_csv(source / "services.csv", low_memory=False)
    mil = pd.read_csv(source / "mileage_timeline_monthly.csv", low_memory=False)
    for frame, columns in [(appt,["created_at","scheduled_at"]),(svc,["delivered_at"]),(mil,["period_end_date"])]:
        for c in columns: frame[c] = pd.to_datetime(frame[c], errors="coerce").dt.normalize()
    ap_groups={k:g for k,g in appt.groupby("motorcycle_id",sort=False)}
    sv_groups={k:g for k,g in svc.groupby("motorcycle_id",sort=False)}
    mi_groups={k:g for k,g in mil.groupby("motorcycle_id",sort=False)}
    values={f:np.full(len(base),np.nan) for f in NEW_FEATURES}
    for mid, landmarks in base.groupby("motorcycle_id",sort=False):
        a=ap_groups.get(mid,appt.iloc[:0]); s=sv_groups.get(mid,svc.iloc[:0]); m=mi_groups.get(mid,mil.iloc[:0])
        matrix=_group_matrix(landmarks.landmark_at,a,s,m); positions=landmarks.index.to_numpy()
        for f,v in matrix.items(): values[f][positions]=v
    out=base.copy()
    for f,v in values.items(): out[f]=v
    forbidden=[c for c in FEATURE_COLUMNS if any(t in c.lower() for t in ["latent","target","censor","days_observed","split","year","future"])]
    checks={
        "base_extended60_exact": list(out.columns[:69]) == list(base.columns[:69]),
        "feature_count_95": len(FEATURE_COLUMNS)==95,
        "all_features_present": set(FEATURE_COLUMNS)<=set(out.columns),
        "forbidden_features_absent": not forbidden,
        "no_latent_columns": not any("latent" in c.lower() for c in out.columns),
        "row_count_preserved": len(out)==len(base),
        "landmark_ids_preserved": out.landmark_id.equals(base.landmark_id),
        "finite_or_missing": bool(np.isfinite(out[NEW_FEATURES].to_numpy(float)[~out[NEW_FEATURES].isna().to_numpy()]).all()),
    }
    output=ml/"derived_outputs/v2_3_v1_5"; output.mkdir(parents=True,exist_ok=True)
    table=output/"v2_3_modeling_table.parquet"; out.to_parquet(table,index=False)
    pd.DataFrame(contract_rows()).to_csv(output/"v2_3_feature_dictionary.csv",index=False)
    metadata={"generated_at_utc":datetime.now(timezone.utc).isoformat(),"rows":len(out),"motorcycles":int(out.motorcycle_id.nunique()),"feature_count":len(FEATURE_COLUMNS),"parent":"V2.2 EXTENDED60","new_feature_groups":GROUPS,"source_hashes":{p.name:_sha256(p) for p in source.glob("*.csv")},"checks":checks,"status":"PASS" if all(checks.values()) else "FAIL"}
    (output/"v2_3_generation_metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    if metadata["status"]!="PASS": raise RuntimeError(checks)
    return metadata


def write_contract(repo_root: Path) -> None:
    root=Path(repo_root); ml=root/"ridebase-ml"; rows=contract_rows()
    yaml=["version: 2.3.0","parent_contract: V2.2_EXTENDED60","feature_count: 95","latent_profiles_allowed: false","point_in_time_cutoff: effective_timestamp_lte_landmark","features:"]
    for row in rows:
        yaml += [f"  - name: {row['name']}",f"    group: {row['group']}",f"    source: {row['source']}",f"    formula: \"{row['formula']}\"",f"    missing_semantics: \"{row['missing_semantics']}\"","    production_derivable: true","    leakage_risk: LOW_WITH_ENFORCED_CUTOFF"]
    (ml/"config/v2_3_feature_contract.yaml").write_text("\n".join(yaml)+"\n")
    md=["# V2.3 Observable Behavior-State Feature Contract","","V2.3 appends 35 point-in-time observable summaries to the frozen V2.2 EXTENDED60 contract. Latent generator profiles, outcomes after the landmark, absolute year, split, target/censor fields and `days_observed` are forbidden.","","| Feature | Group | Source | Formula / cutoff | Missing |","|---|---|---|---|---|"]
    for r in rows: md.append(f"| `{r['name']}` | {r['group']} | {r['source']} | {r['formula']}; effective timestamp <= landmark | {r['missing_semantics']} |")
    md += ["","Every retained feature is available from the same raw history tables in production. Appointment final outcomes are used only after `scheduled_at <= landmark`; an open future appointment is represented solely when `created_at <= landmark`, and its future status is ignored.",""]
    (root/"docs/v2_3_feature_contract.md").write_text("\n".join(md))


if __name__ == "__main__":
    root=Path(__file__).resolve().parents[3]; write_contract(root); print(json.dumps(build(root),indent=2))
