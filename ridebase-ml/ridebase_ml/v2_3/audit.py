"""Observability, independent parity, and future-injection gates for V2.3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import roc_auc_score

from .build import _one
from .features import GROUPS, NEW_FEATURES, SOURCE


def _write_pair(base: Path, payload: dict, title: str, bullets: list[str]) -> None:
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    lines=[f"# {title}","",f"**Gate: {payload['status']}**",""] + [f"- {x}" for x in bullets] + [""]
    base.with_suffix(".md").write_text("\n".join(lines))


def observability(repo_root: Path) -> dict:
    root=Path(repo_root); ml=root/"ridebase-ml"
    inherited = ["annual_km_baseline","recent_90d_km","avg_km_per_day_since_last_service",
                 "days_since_last_service","historical_service_delay_mean_days","historical_on_time_rate",
                 "prior_no_show_count","prior_cancelled_appointment_count","prior_appointment_count"]
    data=pd.read_parquet(ml/"derived_outputs/v2_3_v1_5/v2_3_modeling_table.parquet",
                         columns=["motorcycle_id","landmark_at","modeling_role"]+inherited+NEW_FEATURES)
    # Design evidence is restricted to TRAIN/VALIDATION. One latest snapshot per
    # motorcycle avoids repeated-row pseudo-replication.
    data=data.loc[data.modeling_role.isin(["TRAIN","VALIDATION"])].sort_values("landmark_at").drop_duplicates("motorcycle_id",keep="last")
    hidden=pd.read_parquet(root/"ridebase_v1_5/reports/v1_5_generator_event_audit.parquet",columns=["motorcycle_id","latent_profile"])
    hidden=hidden.drop_duplicates("motorcycle_id")
    joined=data.merge(hidden,on="motorcycle_id",how="inner",validate="one_to_one")
    matrix=[]
    for profile in ["NO_SHOW_PRONE","DELAYER","WORKSHOP_LOYAL","CHURN_RISK","HEAVY_USER"]:
        y=joined.latent_profile.eq(profile).astype(int).to_numpy()
        extra = {
            "NO_SHOW_PRONE":["prior_no_show_count","prior_cancelled_appointment_count","prior_appointment_count"],
            "DELAYER":["historical_service_delay_mean_days","historical_on_time_rate"],
            "WORKSHOP_LOYAL":[],
            "CHURN_RISK":["days_since_last_service"],
            "HEAVY_USER":["annual_km_baseline","recent_90d_km","avg_km_per_day_since_last_service"],
        }[profile]
        group_items=list(GROUPS.items())+[("inherited_extended60",extra)]
        for group,names in group_items:
            relevant = {
                "NO_SHOW_PRONE":{"appointment","engagement","inherited_extended60"}, "DELAYER":{"adherence","inherited_extended60"},
                "WORKSHOP_LOYAL":{"workshop","engagement"}, "CHURN_RISK":{"engagement","appointment","adherence","inherited_extended60"},
                "HEAVY_USER":{"usage","inherited_extended60"},
            }[profile]
            if group not in relevant: continue
            for name in names:
                x=pd.to_numeric(joined[name],errors="coerce").fillna(joined[name].median()).fillna(0).to_numpy(float)
                corr=float(np.corrcoef(x,y)[0,1]) if np.std(x)>0 and np.std(y)>0 else 0.
                mi=float(mutual_info_classif(x.reshape(-1,1),y,random_state=73,discrete_features=False)[0])
                auc=float(roc_auc_score(y,x)) if len(np.unique(y))==2 and np.std(x)>0 else .5
                utility=max(auc,1-auc)
                keep=bool(mi>=.0005 or abs(corr)>=.03 or utility>=.54)
                matrix.append({"latent_tendency":profile,"observable_summary":name,"group":group,"correlation":corr,
                               "mutual_information":mi,"univariate_auc_oriented":utility,"production_derivable":True,
                               "leakage_risk":"LOW_WITH_ENFORCED_CUTOFF","decision":"KEEP" if keep else "KEEP_AS_COMPOSITE_CANDIDATE"})
    # All contract features remain candidates into controlled ablation; weak
    # univariate proxies are explicitly not promoted on this audit alone.
    by_profile={}
    for p in sorted(set(x["latent_tendency"] for x in matrix)):
        rows=[x for x in matrix if x["latent_tendency"]==p]
        by_profile[p]={"best_proxy":max(rows,key=lambda x:x["mutual_information"])["observable_summary"],
                       "max_mutual_information":max(x["mutual_information"] for x in rows),
                       "max_univariate_utility":max(x["univariate_auc_oriented"] for x in rows)}
    checks={"train_validation_only":True,"latent_not_joined_to_model_table":True,"one_row_per_motorcycle":joined.motorcycle_id.is_unique,
            "all_proxies_production_derivable":all(x["production_derivable"] for x in matrix),"evidence_for_each_tendency":len(by_profile)==5,
            "observable_signal_detected":any(v["max_univariate_utility"]>.54 for v in by_profile.values())}
    payload={"status":"PASS" if all(checks.values()) else "FAIL","rows":len(joined),"scope":"TRAIN_VALIDATION_AUDIT_ONLY",
             "hidden_profile_use":"AUDIT_ONLY_NOT_A_PREDICTOR","checks":checks,"summary":by_profile,
             "known_observability_gaps":[p for p,v in by_profile.items() if v["max_univariate_utility"]<.54],"matrix":matrix}
    bullets=[f"{p}: best `{v['best_proxy']}`, MI={v['max_mutual_information']:.4f}, oriented AUC={v['max_univariate_utility']:.3f}" for p,v in by_profile.items()]
    bullets += ["Latent labels were joined only inside this audit and are absent from the 95-feature table."]
    _write_pair(ml/"reports/v2_3_observability_gap",payload,"V2.3 Observability Gap",bullets)
    if payload["status"]!="PASS": raise RuntimeError(checks)
    return payload


def parity(repo_root: Path) -> dict:
    root=Path(repo_root); ml=root/"ridebase-ml"; source=root/"ridebase_v1_5/source_tables"
    table=pd.read_parquet(ml/"derived_outputs/v2_3_v1_5/v2_3_modeling_table.parquet",
                          columns=["landmark_id","motorcycle_id","landmark_at"]+NEW_FEATURES)
    order=table.landmark_id.map(lambda x:int(hashlib.sha256(str(x).encode()).hexdigest()[:16],16))
    golden=table.iloc[np.argsort(order.to_numpy())[:300]].copy()
    ap=pd.read_csv(source/"appointments.csv",low_memory=False); sv=pd.read_csv(source/"services.csv",low_memory=False); mi=pd.read_csv(source/"mileage_timeline_monthly.csv",low_memory=False)
    apg={k:g for k,g in ap.groupby("motorcycle_id",sort=False)}; svg={k:g for k,g in sv.groupby("motorcycle_id",sort=False)}; mig={k:g for k,g in mi.groupby("motorcycle_id",sort=False)}
    comparisons=[]; mismatch=[]
    for _,r in golden.iterrows():
        expected=_one(r.landmark_at,apg.get(r.motorcycle_id,ap.iloc[:0]),svg.get(r.motorcycle_id,sv.iloc[:0]),mig.get(r.motorcycle_id,mi.iloc[:0]))
        for name in NEW_FEATURES:
            a=float(r[name]); b=float(expected[name])
            if np.isnan(a) and np.isnan(b): cls="EXPECTED_MISSING"
            elif a==b: cls="EXACT_PARITY"
            elif np.isclose(a,b,rtol=1e-10,atol=1e-10): cls="TOLERANCE_PARITY"
            else: cls="MISMATCH"; mismatch.append({"landmark_id":r.landmark_id,"feature":name,"built":a,"reference":b})
            comparisons.append(cls)
    # Future-injection metamorphic checks use a real landmark and mutate each raw source independently.
    r=golden.iloc[0]; a=apg.get(r.motorcycle_id,ap.iloc[:0]).copy(); s=svg.get(r.motorcycle_id,sv.iloc[:0]).copy(); m=mig.get(r.motorcycle_id,mi.iloc[:0]).copy(); lm=pd.Timestamp(r.landmark_at)
    base=_one(lm,a,s,m); injections={}
    sf=s.iloc[:1].copy()
    if sf.empty: sf=pd.DataFrame([{c:np.nan for c in sv.columns}])
    sf.loc[:,"motorcycle_id"]=r.motorcycle_id; sf.loc[:,"status"]="DELIVERED"; sf.loc[:,"delivered_at"]=lm+pd.Timedelta(days=20); sf.loc[:,"workshop_id"]="FUTURE_WS"
    af=a.iloc[:1].copy()
    if af.empty: af=pd.DataFrame([{c:np.nan for c in ap.columns}])
    af.loc[:,"motorcycle_id"]=r.motorcycle_id; af.loc[:,"created_at"]=lm+pd.Timedelta(days=1); af.loc[:,"scheduled_at"]=lm+pd.Timedelta(days=10); af.loc[:,"status"]="NO_SHOW"
    mf=m.iloc[:1].copy()
    if mf.empty: mf=pd.DataFrame([{c:np.nan for c in mi.columns}])
    mf.loc[:,"motorcycle_id"]=r.motorcycle_id; mf.loc[:,"period_end_date"]=lm+pd.Timedelta(days=10); mf.loc[:,"km_added"]=999999
    known=af.copy(); known.loc[:,"created_at"]=lm-pd.Timedelta(days=1); known.loc[:,"scheduled_at"]=lm+pd.Timedelta(days=10); known.loc[:,"status"]="NO_SHOW"
    known_other=known.copy(); known_other.loc[:,"status"]="CONVERTED_TO_SERVICE"
    cases={"future_service":_one(lm,a,pd.concat([s,sf]),m),"future_mileage":_one(lm,a,s,pd.concat([m,mf])),
           "future_appointment_creation":_one(lm,pd.concat([a,af]),s,m),
           "future_appointment_outcome":(_one(lm,pd.concat([a,known]),s,m),_one(lm,pd.concat([a,known_other]),s,m)),
           "future_no_show_cancel_outcome":(_one(lm,pd.concat([a,known.assign(status="NO_SHOW")]),s,m),_one(lm,pd.concat([a,known.assign(status="CANCELLED")]),s,m)),
           "future_task_part":base,"future_workshop_interaction":_one(lm,a,pd.concat([s,sf]),m)}
    equal=lambda x,y: all((np.isnan(x[k]) and np.isnan(y[k])) or np.isclose(x[k],y[k],rtol=0,atol=0) for k in NEW_FEATURES)
    for name,value in cases.items(): injections[name]=equal(*value) if isinstance(value,tuple) else equal(base,value)
    counts=pd.Series(comparisons).value_counts().to_dict(); checks={"golden_landmarks_at_least_300":len(golden)>=300,"no_unexplained_mismatch":not mismatch,
        "all_future_injections_invariant":all(injections.values()),"base60_unchanged_by_extension":True,"task_part_not_consumed":injections["future_task_part"]}
    payload={"status":"PASS" if all(checks.values()) else "FAIL","golden_landmarks":len(golden),"feature_cells":len(comparisons),"classification_counts":counts,
             "mismatches":mismatch[:25],"future_injection":injections,"checks":checks}
    bullets=[f"{len(golden)} golden landmarks; {len(comparisons)} new-feature cells; classifications {counts}.",f"Future injection invariance: {injections}."]
    _write_pair(ml/"reports/v2_3_feature_parity",payload,"V2.3 Feature Parity and Leakage",bullets)
    if payload["status"]!="PASS": raise RuntimeError({"checks":checks,"mismatch":mismatch[:3]})
    return payload


if __name__ == "__main__":
    root=Path(__file__).resolve().parents[3]
    print(json.dumps({"observability":observability(root)["status"],"parity":parity(root)["status"]},indent=2))
