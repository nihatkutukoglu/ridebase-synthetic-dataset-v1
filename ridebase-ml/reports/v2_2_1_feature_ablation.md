# V2.2.1 Feature Ablation

**TEST untouched.**

| feature_set                                   |   features |   search_ipcw_c |   final_ipcw_c |   final_ibs | calibration              | behavior   | eligible   |
|:----------------------------------------------|-----------:|----------------:|---------------:|------------:|:-------------------------|:-----------|:-----------|
| CORE54                                        |         54 |        0.744734 |       0.710513 |    0.172521 | isotonic_beta_blend_0.75 | FAIL       | False      |
| EXTENDED60                                    |         60 |        0.752325 |       0.718876 |    0.168764 | isotonic_beta_blend_0.75 | PASS       | True       |
| CORE54_PLUS_PRIOR_APPOINTMENT_COUNT           |         55 |        0.744784 |       0.70996  |    0.17273  | isotonic_beta_blend_0.75 | FAIL       | False      |
| CORE54_PLUS_PRIOR_NO_SHOW_COUNT               |         55 |        0.744769 |       0.710062 |    0.172578 | isotonic_beta_blend_0.75 | FAIL       | False      |
| CORE54_PLUS_PRIOR_CANCELLED_APPOINTMENT_COUNT |         55 |        0.744634 |       0.709845 |    0.172732 | isotonic_beta_blend_0.75 | FAIL       | False      |
| CORE54_PLUS_KNOWN_APPOINTMENT_WITHIN_30D      |         55 |        0.751722 |       0.718114 |    0.168919 | isotonic_beta_blend_0.75 | PASS       | False      |
| CORE54_PLUS_DAYS_TO_NEXT_KNOWN_APPOINTMENT    |         55 |        0.747682 |       0.713721 |    0.171298 | isotonic_beta_blend_0.75 | FAIL       | False      |
| CORE54_PLUS_RECENT_BREAKDOWN_COUNT_180D       |         55 |        0.744858 |       0.710238 |    0.172705 | isotonic_beta_blend_0.75 | FAIL       | False      |
| CORE54_PLUS_APPOINTMENT_INTENT                |         56 |        0.752049 |       0.718225 |    0.169174 | isotonic_beta_blend_0.75 | PASS       | False      |
| CORE54_PLUS_NOSHOW_APPOINTMENT                |         57 |        0.752202 |       0.718824 |    0.169179 | isotonic                 | PASS       | True       |
| STABLE58                                      |         58 |        0.752363 |       0.718704 |    0.168912 | isotonic_beta_blend_0.75 | PASS       | True       |
| EXTENDED59_MINUS_BREAKDOWN180                 |         59 |        0.752572 |       0.718368 |    0.16902  | isotonic_beta_blend_0.75 | PASS       | True       |
