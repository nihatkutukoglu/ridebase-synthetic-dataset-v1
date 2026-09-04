# V2.2.1 Overdue / High-Usage Audit

**Gate: PASS — TEST untouched**

|   annual_km | profile         | maintenance_state   | maintenance_due_now   |    p30 |    p60 |    p90 |   p120 |
|------------:|:----------------|:--------------------|:----------------------|-------:|-------:|-------:|-------:|
|       30000 | ADHERENT        | NOT_DUE             | False                 | 0.4611 | 0.8373 | 0.9396 | 0.9738 |
|       30000 | ADHERENT        | NEAR_DUE            | False                 | 0.6084 | 0.9080 | 0.9631 | 0.9797 |
|       30000 | ADHERENT        | OVERDUE             | True                  | 0.6181 | 0.9106 | 0.9634 | 0.9797 |
|       30000 | ADHERENT        | SEVERE_OVERDUE      | True                  | 0.6222 | 0.9111 | 0.9635 | 0.9797 |
|       30000 | NORMAL          | NOT_DUE             | False                 | 0.2310 | 0.5462 | 0.7996 | 0.9067 |
|       30000 | NORMAL          | NEAR_DUE            | False                 | 0.2902 | 0.6597 | 0.8524 | 0.9353 |
|       30000 | NORMAL          | OVERDUE             | True                  | 0.3073 | 0.6668 | 0.8574 | 0.9375 |
|       30000 | NORMAL          | SEVERE_OVERDUE      | True                  | 0.3081 | 0.6682 | 0.8583 | 0.9379 |
|       30000 | DELAYER_NO_SHOW | NOT_DUE             | False                 | 0.2025 | 0.4745 | 0.7161 | 0.8687 |
|       30000 | DELAYER_NO_SHOW | NEAR_DUE            | False                 | 0.2310 | 0.5461 | 0.7996 | 0.9067 |
|       30000 | DELAYER_NO_SHOW | OVERDUE             | True                  | 0.2389 | 0.5522 | 0.8055 | 0.9101 |
|       30000 | DELAYER_NO_SHOW | SEVERE_OVERDUE      | True                  | 0.2394 | 0.5568 | 0.8066 | 0.9108 |
|       60000 | ADHERENT        | NOT_DUE             | False                 | 0.4782 | 0.8448 | 0.9414 | 0.9741 |
|       60000 | ADHERENT        | NEAR_DUE            | False                 | 0.6251 | 0.9117 | 0.9635 | 0.9797 |
|       60000 | ADHERENT        | OVERDUE             | True                  | 0.6347 | 0.9135 | 0.9637 | 0.9797 |
|       60000 | ADHERENT        | SEVERE_OVERDUE      | True                  | 0.6365 | 0.9138 | 0.9637 | 0.9824 |
|       60000 | NORMAL          | NOT_DUE             | False                 | 0.2443 | 0.5579 | 0.8170 | 0.9113 |
|       60000 | NORMAL          | NEAR_DUE            | False                 | 0.3087 | 0.6694 | 0.8591 | 0.9382 |
|       60000 | NORMAL          | OVERDUE             | True                  | 0.3156 | 0.7135 | 0.8801 | 0.9501 |
|       60000 | NORMAL          | SEVERE_OVERDUE      | True                  | 0.3165 | 0.7211 | 0.8809 | 0.9504 |
|       60000 | DELAYER_NO_SHOW | NOT_DUE             | False                 | 0.2049 | 0.4877 | 0.7406 | 0.8748 |
|       60000 | DELAYER_NO_SHOW | NEAR_DUE            | False                 | 0.2443 | 0.5579 | 0.8170 | 0.9113 |
|       60000 | DELAYER_NO_SHOW | OVERDUE             | True                  | 0.2708 | 0.6091 | 0.8358 | 0.9283 |
|       60000 | DELAYER_NO_SHOW | SEVERE_OVERDUE      | True                  | 0.2737 | 0.6112 | 0.8369 | 0.9291 |

Maintenance Due is deterministic policy state; Service Return Risk models customer return behavior. They are not interchangeable.
