# V2.2 Overdue / High-Usage Product Audit

**Gate: PASS**

| profile         | maintenance_state   | maintenance_due_now   |    p30 |    p60 |    p90 |   p120 |
|:----------------|:--------------------|:----------------------|-------:|-------:|-------:|-------:|
| ADHERENT        | NOT_DUE             | False                 | 0.4852 | 0.8717 | 0.9589 | 0.9814 |
| ADHERENT        | NEAR_DUE            | False                 | 0.6401 | 0.9157 | 0.9589 | 0.9814 |
| ADHERENT        | OVERDUE             | True                  | 0.6401 | 0.9176 | 0.9631 | 0.9814 |
| ADHERENT        | SEVERE_OVERDUE      | True                  | 0.6401 | 0.9176 | 0.9631 | 0.9814 |
| NORMAL          | NOT_DUE             | False                 | 0.2637 | 0.5750 | 0.8308 | 0.9183 |
| NORMAL          | NEAR_DUE            | False                 | 0.2925 | 0.6755 | 0.8745 | 0.9402 |
| NORMAL          | OVERDUE             | True                  | 0.2925 | 0.6755 | 0.8745 | 0.9545 |
| NORMAL          | SEVERE_OVERDUE      | True                  | 0.2925 | 0.6929 | 0.8745 | 0.9545 |
| DELAYER_NO_SHOW | NOT_DUE             | False                 | 0.2192 | 0.5380 | 0.7879 | 0.9014 |
| DELAYER_NO_SHOW | NEAR_DUE            | False                 | 0.2637 | 0.5750 | 0.8308 | 0.9183 |
| DELAYER_NO_SHOW | OVERDUE             | True                  | 0.2637 | 0.5750 | 0.8308 | 0.9183 |
| DELAYER_NO_SHOW | SEVERE_OVERDUE      | True                  | 0.2637 | 0.5750 | 0.8387 | 0.9301 |

Maintenance Due is a deterministic policy state. Service Return Risk is customer behavior probability; the two are intentionally not interchangeable.
