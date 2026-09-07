# V3 Phase 20 — Oracle Gap Study

# RESEARCH ORACLE — NOT DEPLOYABLE

The oracle model consumes **pure future information** about the target service. It
exists only to size how much of V3's remaining error is reducible at all. It is
never trained into a candidate production model, never written to a frozen
artifact, and its features never enter `V3Dataset.features` — `cmd_oracle` builds
them in a throwaway frame, and
`test_no_oracle_or_latent_feature_reaches_the_dataset` asserts no column starting
with `ORACLE_` can appear in the real dataset.

Data: [`20_oracle_gap.csv`](20_oracle_gap.csv).

## Oracle features

| feature | why it is forbidden in production |
|---|---|
| `ORACLE_lead_days` | days from landmark to the target service — unknowable at the landmark |
| `ORACLE_target_km_delta` | kilometres ridden between landmark and target service |
| `ORACLE_target_type_{PERIODIC,REPAIR,TIRE,BREAKDOWN}` | what kind of visit it turns out to be |

Together these amount to *knowing exactly when the customer next shows up and why*.

## Result

| model | n features | micro F1 | macro F1 | mAP | micro PR-AUC | P@3 | R@3 |
|---|---|---|---|---|---|---|---|
| observable_champion_family | 277 | 0.4215 | 0.2234 | 0.1650 | 0.5771 | 0.5008 | 0.5690 |
| RESEARCH_ORACLE | 283 | 0.4647 | 0.2992 | 0.2372 | 0.6431 | 0.5152 | 0.6037 |

| metric | observable | oracle | gap | relative |
|---|---|---|---|---|
| mAP | 0.1650 | 0.2372 | +0.0722 | +44% |
| micro PR-AUC | 0.5771 | 0.6431 | +0.0660 | +11% |
| micro F1 | 0.4215 | 0.4647 | +0.0432 | +10% |
| P@3 | 0.5008 | 0.5152 | +0.0144 | +3% |

## Interpretation

**The oracle gap is large on ranking and small on the top-K product surface.**
Perfect knowledge of the next visit lifts mAP by 44% but moves P@3 by only
3%. The top of the list — the part a workshop actually reads — is
close to its ceiling already; the gain is concentrated in the long tail of
mid-prevalence labels whose ordering depends on how far in the future the visit is.

**The missing observable is next-visit timing and type.** That is not a feature
anyone forgot to build: it is genuinely unknown at the landmark. It is also
precisely the quantity V2.1 estimates.

**V3 does not and must not consume V2.1's output.** Feeding V2.1 P30/P60/P90/P120
into V3 would couple two surfaces the product deliberately keeps separate, would
propagate V2.1's calibration error into V3's displayed percentages, and would make
a V3 number move whenever V2.1 was retrained. The observation here is a *research*
finding about where the ceiling comes from, not a design recommendation. If that
coupling is ever considered it needs its own contract, its own audit, and its own
decision — it is out of scope for V3.0 and is not implemented.

**Even the oracle is far from perfect** (mAP 0.2372). The residual is the
irreducible stochastic layer identified in Phase 9: the inspection-bundle draw and
the random fault/finding events. Knowing exactly when the bike arrives still does
not tell you which coin the generator flipped.
