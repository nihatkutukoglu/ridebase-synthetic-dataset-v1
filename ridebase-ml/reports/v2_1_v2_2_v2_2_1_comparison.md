# V2.1 vs V2.2 vs V2.2.1

| model   | world_status            |   ipcw_c |      ibs |   mean_calibration_error |   p30_unique |   unseen_ipcw_c |   unseen_ibs |
|:--------|:------------------------|---------:|---------:|-------------------------:|-------------:|----------------:|-------------:|
| V2.1    | V1.4 / production       | 0.752681 | 0.101995 |                 0.042362 |          126 |        0.756368 |     0.101857 |
| V2.2    | V1.5 / frozen offline   | 0.708029 | 0.123775 |                 0.059952 |           94 |        0.715722 |     0.122099 |
| V2.2.1  | V1.5 / recovery offline | 0.708029 | 0.123575 |                 0.063003 |        21217 |        0.715722 |     0.122133 |

V2.1 was evaluated in V1.4; V2.2/V2.2.1 use V1.5. Cross-world values are contextual only.

Decision: `CHALLENGER_REJECTED_STATISTICAL`. V2.1 remains production champion.
