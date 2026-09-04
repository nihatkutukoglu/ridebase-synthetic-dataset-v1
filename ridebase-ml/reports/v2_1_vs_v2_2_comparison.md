# Frozen V2.1 vs Offline V2.2 Challenger

| criterion                |     v2_1 |     v2_2 | v2_2_gate   |
|:-------------------------|---------:|---------:|:------------|
| IPCW C-index             | 0.752681 | 0.708029 | PASS        |
| Harrell C                | 0.752737 | 0.708108 | REPORT      |
| IBS 30-120               | 0.101995 | 0.123775 | PASS        |
| P30 exact-zero share     | 0.000000 | 0.000000 | PASS        |
| P90 calibration error    | 0.046369 | 0.074752 | PASS        |
| Unseen motorcycle IPCW C | 0.756368 | 0.715722 | PASS        |

Metrics come from different synthetic worlds and are not a paired causal comparison.

Decision: `CHALLENGER_ACCEPTED` for offline/shadow use only. V2.1 remains production champion.
