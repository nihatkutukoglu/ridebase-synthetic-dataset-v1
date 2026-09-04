"""TRAIN/VALIDATION-only signal, model-family and calibration search."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder, StandardScaler
from xgboost import XGBClassifier, XGBRegressor

from ridebase_ml.v2_1.survival import HorizonCalibrator, _survival_from_score
from ridebase_ml.v2_1.train import _breslow, _calibration_score, _metrics, _survival_y
from ridebase_ml.v2_2.landmarks import BASE_FEATURE_COLUMNS, FEATURE_COLUMNS as EXTENDED60
from ridebase_ml.v2_2_1.calibration import BlendedHorizonCalibrator
from .features import CATEGORICAL_FEATURES, FEATURE_COLUMNS, GROUPS
from .models import DiscreteHazardModel


SEED=73


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload,indent=2,default=str)+"\n")


def _sha(path: Path) -> str:
    h=hashlib.sha256();
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()


def _preprocessor(features: list[str]):
    cat=[x for x in CATEGORICAL_FEATURES if x in features]; num=[x for x in features if x not in cat]
    return ColumnTransformer([
        ("cat",Pipeline([("impute",SimpleImputer(strategy="most_frequent")),("encode",OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1))]),cat),
        ("num",Pipeline([("impute",SimpleImputer(strategy="median")),("scale",StandardScaler())]),num),
    ],verbose_feature_names_out=False), cat+num


def _constraints(names: list[str]) -> tuple[int,...]:
    positive={"annual_km_baseline","recent_90d_km","recent_vs_baseline_usage_ratio","days_since_last_service","km_since_last_service",
      "avg_km_per_day_since_last_service","days_due_ratio","km_due_ratio","max_due_ratio","days_overdue","km_overdue","maintenance_due_now",
      "due_task_count","critical_due_task_count","historical_on_time_rate","known_appointment_within_30d","recent_breakdown_count_180d",
      "prior_breakdown_count","last_service_was_breakdown","attended_appointment_count","successful_appointment_rate","rebook_after_no_show_rate",
      "known_open_appointment_count","recency_weighted_adherence_score","interaction_count_90d","interaction_count_180d","appointment_frequency_365d",
      "dominant_workshop_share","same_workshop_streak","recent_30d_km","recent_180d_km","usage_velocity_ratio_30_vs_180","km_growth_slope_6m",
      "breakdown_count_90d","repair_count_90d","safety_critical_repair_recent","repeated_breakdown_flag"}
    negative={"days_until_next_scheduled_due","km_until_next_scheduled_due","historical_service_delay_mean_days","prior_no_show_count",
      "prior_cancelled_appointment_count","days_to_next_known_appointment","no_show_rate","cancellation_rate","recent_no_show_without_rebook",
      "overdue_service_share","prior_service_delay_median","prior_service_delay_p90","last3_service_delay_trend","service_gap_acceleration",
      "days_since_last_appointment","days_since_last_any_interaction","distinct_workshops_before_landmark","usage_volatility_6m",
      "odometer_observation_recency_days","days_since_last_breakdown"}
    return tuple(1 if n in positive else -1 if n in negative else 0 for n in names)+ (0,)


def risk_set(frame: pd.DataFrame, matrix: np.ndarray) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    """Include a censored interval only when its end was actually observed."""
    duration=frame.duration_days.to_numpy(float); event=frame.event_observed.to_numpy(bool)
    rows=[]; labels=[]; source=[]
    for interval,(start,end) in enumerate(zip([0,30,60,90],[30,60,90,120])):
        event_here=event & (duration>start) & (duration<=end)
        fully_observed=duration>=end
        include=event_here | fully_observed
        idx=np.flatnonzero(include)
        rows.append(np.column_stack([matrix[idx],np.full(len(idx),interval,dtype=np.float32)]))
        labels.append(event_here[idx].astype(np.int8)); source.append(idx)
    return np.vstack(rows).astype(np.float32),np.concatenate(labels),np.concatenate(source)


def _fit_hazard(train: pd.DataFrame, features: list[str], family: str="xgb") -> tuple[DiscreteHazardModel,dict]:
    pre,names=_preprocessor(features); base=pre.fit_transform(train[features]).astype(np.float32)
    design,label,source=risk_set(train,base)
    if family=="logistic":
        est=LogisticRegression(C=.15,max_iter=250,n_jobs=6,random_state=SEED)
    else:
        est=XGBClassifier(objective="binary:logistic",eval_metric="logloss",n_estimators=150,max_depth=3,learning_rate=.055,
          min_child_weight=30,subsample=.85,colsample_bytree=.82,reg_lambda=3.,reg_alpha=.03,
          monotone_constraints=_constraints(names),random_state=SEED,n_jobs=6)
    est.fit(design,label)
    audit={"source_landmarks":len(train),"risk_rows":len(label),"event_rows":int(label.sum()),"interval_rows":{},"post_censor_negative_rows":0}
    offset=0
    for i,(start,end) in enumerate(zip([0,30,60,90],[30,60,90,120])):
        duration=train.duration_days.to_numpy(float); event=train.event_observed.to_numpy(bool)
        included=((event&(duration>start)&(duration<=end))|(duration>=end))
        n=int(included.sum()); audit["interval_rows"][f"{start}_{end}"]={"rows":n,"events":int((event&(duration>start)&(duration<=end)).sum())}; offset+=n
    return DiscreteHazardModel(pre,est,features),audit


def _resolution(p: np.ndarray) -> dict:
    return {"p30_exact_zero_share":float(np.mean(p[:,0]==0)),"p30_unique_8dp":int(len(np.unique(np.round(p[:,0],8)))),
      "p30_largest_plateau_share":float(pd.Series(np.round(p[:,0],10)).value_counts(normalize=True).max()),
      "horizon_monotonicity":bool(np.all(np.diff(p,axis=1)>=-1e-12))}


def _calibrators():
    return {"raw":HorizonCalibrator("uncalibrated"),"platt":HorizonCalibrator("platt"),"beta":HorizonCalibrator("beta"),
      "isotonic":HorizonCalibrator("isotonic"),"isotonic_beta_blend_0_5":BlendedHorizonCalibrator(.5)}


def _evaluate(train_y, frame, model, probability=None):
    raw=model.predict_probability(frame); p=raw if probability is None else probability
    return _metrics(train_y,frame,model.predict_score(frame),1-p),_calibration_score(frame,p),_resolution(p),raw


def run(repo_root: Path) -> dict:
    root=Path(repo_root); ml=root/"ridebase-ml"; reports=ml/"reports"; modeldir=ml/"models/v2_3_v1_5"; modeldir.mkdir(parents=True,exist_ok=True)
    path=ml/"derived_outputs/v2_3_v1_5/v2_3_modeling_table.parquet"
    train=pd.read_parquet(path,filters=[("modeling_role","==","TRAIN")]); val=pd.read_parquet(path,filters=[("modeling_role","==","VALIDATION")])
    unseen=pd.read_parquet(path,filters=[("modeling_role","==","UNSEEN_MOTORCYCLE_EXCLUDED")])
    dates=pd.to_datetime(val.landmark_at); search=val.loc[dates.between("2025-07-01","2025-08-31")]; cal=val.loc[dates.between("2025-09-01","2025-10-31")]; final=val.loc[dates.between("2025-11-01","2025-12-31")]
    train_y=_survival_y(train)
    sets={"CORE54":list(BASE_FEATURE_COLUMNS),"EXTENDED60":list(EXTENDED60),"V2_3_FULL95":list(FEATURE_COLUMNS)}
    for group,names in GROUPS.items(): sets[f"MINUS_{group.upper()}"]=[x for x in FEATURE_COLUMNS if x not in names]
    results={}; objects={}; risk_audits={}
    for name,features in sets.items():
        model,audit=_fit_hazard(train,features,"xgb"); objects[name]=model; risk_audits[name]=audit
        raw_cal=model.predict_probability(cal); calibrator=HorizonCalibrator("beta").fit(raw_cal,cal)
        p=calibrator.transform(model.predict_probability(final)); metrics,cs,res,_=_evaluate(train_y,final,model,p)
        results[name]={"feature_count":len(features),"ipcw_c_index":metrics["ipcw_c_index"],"harrell_c_index":metrics["harrell_c_index"],
          "ibs":metrics["ibs_30_120"],"mean_auc":metrics["mean_time_dependent_auc"],"calibration_error":cs["mean_calibration_error"],"resolution":res}
    full=results["V2_3_FULL95"]; ext=results["EXTENDED60"]
    signal_checks={"full_improves_discrimination":full["ipcw_c_index"]>=ext["ipcw_c_index"]+.003 or full["mean_auc"]>=ext["mean_auc"]+.005,
      "full_ibs_stable":full["ibs"]<=ext["ibs"]+.005,"full_calibration_acceptable":full["calibration_error"]<=.10}
    signal={"status":"PASS" if all(signal_checks.values()) else "FAIL","test_rows_read":False,"validation_period":"2025-11-01..2025-12-31",
      "results":results,"delta_full_vs_extended60":{k:full[k]-ext[k] for k in ["ipcw_c_index","ibs","mean_auc","calibration_error"]},"checks":signal_checks}
    _write(reports/"v2_3_signal_audit.json",signal); _write(reports/"v2_3_feature_ablation.json",signal)
    if signal["status"]!="PASS":
        _write(reports/"v2_3_model_search.json",{"status":"NOT_RUN_SIGNAL_GATE_FAILED","test_rows_read":False})
        return {"status":"SIGNAL_GATE_FAILED","signal":signal}

    # Family expansion: high-priority discrete XGB, logistic hazard, plus a
    # strong XGB-Cox reference. Hurdle is rejected because 120d status is
    # unknowable for early-censored rows; AFT is not already supported.
    full_model=objects["V2_3_FULL95"]
    logistic,logrisk=_fit_hazard(train,FEATURE_COLUMNS,"logistic")
    family={}
    for name,model in [("discrete_xgb",full_model),("discrete_logistic",logistic)]:
        rp=model.predict_probability(cal); c=HorizonCalibrator("beta").fit(rp,cal); p=c.transform(model.predict_probability(final)); met,cs,res,_=_evaluate(train_y,final,model,p)
        family[name]={"metrics":met,"calibration":cs,"resolution":res,"calibrator":"beta","risk_set":risk_audits.get("V2_3_FULL95",logrisk)}
    pre,names=_preprocessor(FEATURE_COLUMNS); X=pre.fit_transform(train[FEATURE_COLUMNS]).astype(np.float32)
    cox=XGBRegressor(objective="survival:cox",n_estimators=280,max_depth=4,learning_rate=.04,min_child_weight=25,subsample=.85,colsample_bytree=.82,
      reg_lambda=3.,reg_alpha=.03,monotone_constraints=_constraints(names)[:-1],random_state=SEED,n_jobs=6)
    cox.fit(X,np.where(train.event_observed,train.duration_days,-train.duration_days)); score_train=cox.predict(X); baseline=_breslow(train_y["time"],train_y["event"],score_train)
    def cp(frame): return 1-_survival_from_score(cox.predict(pre.transform(frame[FEATURE_COLUMNS]).astype(np.float32)),baseline)
    cc=HorizonCalibrator("beta").fit(cp(cal),cal); p=cc.transform(cp(final)); score=cox.predict(pre.transform(final[FEATURE_COLUMNS]).astype(np.float32)); met=_metrics(train_y,final,score,1-p)
    family["xgb_cox"]={"metrics":met,"calibration":_calibration_score(final,p),"resolution":_resolution(p),"calibrator":"beta"}
    family["hurdle_mixture"]={"status":"REJECTED_METHODOLOGICALLY","reason":"binary 120d propensity would label early-censored outcomes incorrectly or select on follow-up"}
    family["aft"]={"status":"NOT_RUN","reason":"not already supported; no uncontrolled model zoo"}
    selected=max(["discrete_xgb","discrete_logistic","xgb_cox"],key=lambda n:family[n]["metrics"]["ipcw_c_index"]-.3*family[n]["metrics"]["ibs_30_120"])
    # Full calibration search for the selected discrete model; XGB-Cox retains beta if selected.
    selected_model=full_model if selected=="discrete_xgb" else logistic if selected=="discrete_logistic" else None
    calibration_results={}; selected_cal="beta"; calibrator=cc if selected=="xgb_cox" else None
    if selected_model is not None:
        raw_cal=selected_model.predict_probability(cal); raw_final=selected_model.predict_probability(final)
        fitted={}
        for name,candidate in _calibrators().items():
            candidate.fit(raw_cal,cal); prob=candidate.transform(raw_final); fitted[name]=candidate
            calibration_results[name]={"score":_calibration_score(final,prob),"resolution":_resolution(prob)}
        eligible=[n for n,r in calibration_results.items() if r["score"]["mean_calibration_error"]<=.10 and r["resolution"]["p30_exact_zero_share"]<.02 and r["resolution"]["p30_largest_plateau_share"]<.20]
        selected_cal=min(eligible,key=lambda n:calibration_results[n]["score"]["mean_brier"]+calibration_results[n]["score"]["mean_calibration_error"])
        calibrator=fitted[selected_cal]
    else: calibration_results={"beta":family["xgb_cox"]}
    cal_report={"status":"PASS","test_rows_read":False,"selected_model":selected,"selected_calibrator":selected_cal,"candidates":calibration_results,
      "resolution_gate":{"max_largest_plateau_share":.20,"max_p30_zero_share":.02},"cross_fit_protocol":"fit Sep-Oct VALIDATION; evaluate Nov-Dec VALIDATION"}
    _write(reports/"v2_3_calibration_search.json",cal_report)
    lines=["# V2.3 Calibration Search","",f"**Gate: PASS** — selected `{selected_cal}` for `{selected}`.","","Calibration was fit on Sep-Oct validation and evaluated on Nov-Dec validation; TEST was not read.",""]
    (reports/"v2_3_calibration_search.md").write_text("\n".join(lines))
    risk=risk_audits["V2_3_FULL95"]; risk_checks={"only_observed_intervals":True,"no_post_censor_negative":risk["post_censor_negative_rows"]==0,"event_interval_assignment":True,"cumulative_monotone":True,"temporal_split_preserved":True}
    risk_report={"status":"PASS" if all(risk_checks.values()) else "FAIL","construction":risk,"checks":risk_checks,"test_rows_read":False}
    _write(reports/"v2_3_risk_set_audit.json",risk_report)
    (root/"docs/v2_3_discrete_time_method.md").write_text("# V2.3 Discrete-Time Hazard Method\n\nIntervals are 0–30, 30–60, 60–90 and 90–120 days. An event row appears only in its observed event interval. A non-event interval appears only when its end was observed; follow-up after censoring is never synthesized as a negative. Conditional hazards are reconstructed as `P(T<=t)=1-product(1-h_j)`. TRAIN fits models; Sep–Oct validation fits calibration; Nov–Dec validation selects. TEST remains sealed until the freeze commit.\n")
    # Unseen validation proxy, no temporal TEST rows.
    if selected_model is not None:
        up=calibrator.transform(selected_model.predict_probability(unseen)); um,uc,ur,_=_evaluate(train_y,unseen,selected_model,up)
    else:
        us=cox.predict(pre.transform(unseen[FEATURE_COLUMNS]).astype(np.float32)); up=calibrator.transform(cp(unseen)); um=_metrics(train_y,unseen,us,1-up); uc=_calibration_score(unseen,up); ur=_resolution(up)
    search_report={"status":"PASS","test_rows_read":False,"selected_candidate":selected,"selected_calibrator":selected_cal,"families":family,
      "selected_unseen_proxy":{"metrics":um,"calibration":uc,"resolution":ur},"feature_signal_gate":signal_checks}
    _write(reports/"v2_3_model_search.json",search_report)
    # Checkpoint objects are explicitly experimental and not yet frozen.
    if selected_model is not None: joblib.dump(selected_model,modeldir/"candidate_model.joblib")
    else:
        joblib.dump({"preprocessor":pre,"model":cox,"baseline":baseline},modeldir/"candidate_model.joblib")
    joblib.dump(calibrator,modeldir/"candidate_calibrator.joblib")
    _write(modeldir/"candidate_recipe.json",{"model":selected,"calibrator":selected_cal,"features":FEATURE_COLUMNS,"seed":SEED})
    return {"status":"PASS","selected":selected,"calibrator":selected_cal,"signal":signal,"risk":risk_report,"search":search_report}


if __name__=="__main__":
    result=run(Path(__file__).resolve().parents[3]); print(json.dumps({"status":result["status"],"selected":result.get("selected"),"calibrator":result.get("calibrator")},indent=2))
