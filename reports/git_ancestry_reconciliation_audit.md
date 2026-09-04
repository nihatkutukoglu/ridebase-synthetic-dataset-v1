# Phase 1 — Git Ancestry Reconciliation Audit

## `git merge-base --is-ancestor` results

| Commit | vs HEAD (4b84aac) | vs origin/main |
|---|---|---|
| `7272fa6` (Deploy maintenance urgency Control Center update) | **INCLUDED** | **INCLUDED** |
| `b3467eb` (Record maintenance urgency live verification) | **INCLUDED** | **INCLUDED** |

`git fetch origin` ran first; `origin/main` == `HEAD` == `4b84aac` both before
and after the fetch — no divergence.

## Ancestry is formal, not just name-based

`git log --graph --oneline --all -40` shows a single linear chain — `7272fa6`
and `b3467eb` are 27 and 25 commits behind HEAD respectively, no merges, no
rebase/squash markers. `git show --stat --oneline` on each:

- `7272fa6`: touched `RideBase_Control_Center.{html,full.html}`, `public/index.html`,
  `manifest.json` — +514/−7, the urgency card's initial UI ship.
- `b3467eb`: added `reports/maintenance_urgency_live_*` + `scripts/audit_maintenance_urgency_live_e2e.py` — the live-verification artifacts.
- `4b84aac`: the FAZ1-5 commit — 35 files, +4036/−930, does not touch
  maintenance-urgency logic itself (only vocabulary rename `driving_metric`
  DAYS→TIME, which the urgency code already produced under a different key).

**Verdict: ancestry PASS.** No reconciliation needed — proceeding straight to
content verification for completeness per the mission brief.

## Content verification (not just commit presence)

Grepped current HEAD's working tree for each required symbol:

| Symbol | Backend (`v2_scenario.py`, `policy/urgency.py`) | Frontend (`template.html` + built artifacts) | Tests |
|---|---|---|---|
| `maintenance_urgency_score` | ✅ | ✅ | ✅ |
| `maintenance_urgency_level` | ✅ | ✅ | ✅ |
| `maintenance_urgency_reason` | ✅ | ✅ | ✅ |
| `determining_dimension` | ✅ | ✅ | ✅ |
| `progress_ratio` | ✅ | ✅ | ✅ |

**Canonical backend calculation**: `calculate_maintenance_urgency()` in
`ridebase-ml/ridebase_ml/policy/urgency.py` — pure, deterministic,
"completely independent of machine learning models" (its own docstring).
Piecewise-linear 0–100 score by `progress_ratio`, saturating at **100 for
R ≥ 5.0** (confirms the Phase-7 expectation), 5-band severity
(NORMAL/YAKLAŞIYOR/GECİKMİŞ/ÇOK GECİKMİŞ/KRİTİK) with an explicit invariant
("If progress_ratio >= 1.0, level must never be NORMAL or YAKLAŞIYOR").
Called from `_maintenance_assessment()` in `app/v2_scenario.py:374`, which
also computes `km_progress_ratio`/`time_progress_ratio` and picks the
binding dimension via `max(progress, key=...)`.

**Frontend backend-first usage confirmed at `template.html:2205`**
(`v2CalculateUrgency`): builds `hasCanonical` from the 5 backend fields above,
and when true returns `source: "BACKEND_CANONICAL"` directly from the
response — with the code comment "**Fallback only; backend urgency fields
are canonical.**" immediately above the branch.

**Fallback-only urgency calculation**: still present (`v2CalculateUrgency`'s
`hasKmRatio`/else-path continues past line ~2245), but only reachable when
`hasCanonical` is false — i.e. genuinely fallback, not primary.

**Non-mechanical copy check**: grepped for "arıza"/"bozulma"/"breakdown
probability"/"failure probability" near urgency/V2.1 text — the two hits
that exist are unrelated (one about model packaging integrity in a QA tip,
one explicitly *disclaiming* that failure/spend history is fabricated). No
urgency or V2.1 output is worded as a mechanical failure/breakdown
probability anywhere in the current template.

**Tests**: `ridebase-v1-dashboard/backend/tests/test_maintenance_urgency_api.py`
(100 lines) and `ridebase-ml/tests/test_maintenance_urgency.py` both present
and part of the suites run in Phase 3/9.

## Conclusion

Both named commits are true ancestors of current HEAD/origin/main, and their
functionality is not just present in history but live in the current file
tree, wired backend-first with the documented fallback pattern. **No
Maintenance Urgency work is missing. No reconciliation, cherry-pick, or
history rewrite is required.** Proceeding to Phase 2.
