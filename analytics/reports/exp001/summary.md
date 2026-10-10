| policy | set | n | survival | kills | hunt success | energy/kill | invalid atk | give-ups | death rate |
|---|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map | 20 | 2000 ± 0 | 2.10 ± 0.44 | 0.12 ± 0.05 | 127 ± 58 | 0.56 ± 0.14 | 3.2 ± 1.7 | 0.00 |
| random | eval_seen_map | 20 | 1763 ± 143 | 0.20 ± 0.40 | 0.04 ± 0.07 | 172 ± 16 | 0.99 ± 0.01 | 211.9 ± 41.0 | 0.80 |
| ppo_v0_s0 | eval_seen_map | 20 | 1655 ± 78 | 0.00 ± 0.00 | 0.00 ± 0.00 | – | 0.00 ± 0.00 | 150.3 ± 330.4 | 1.00 |
| ppo_v0_s1 | eval_seen_map | 20 | 1675 ± 64 | 0.00 ± 0.00 | 0.00 ± 0.00 | – | 0.00 ± 0.00 | 64.2 ± 254.2 | 0.95 |
| ppo_v0_s2 | eval_seen_map | 20 | 1687 ± 89 | 0.00 ± 0.00 | 0.00 ± 0.00 | – | 0.00 ± 0.00 | 157.2 ± 316.2 | 0.95 |

행동 분포 (비율)

| policy | set | SEARCH | APPROACH | CHASE | ATTACK | GO_TO_WATER | REST | GIVE_UP |
|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map | 0.11 | 0.06 | 0.19 | 0.02 | 0.05 | 0.56 | 0.00 |
| random | eval_seen_map | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 |
| ppo_v0_s0 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.18 | 0.80 |
| ppo_v0_s1 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.21 | 0.00 | 0.79 |
| ppo_v0_s2 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.25 | 0.43 | 0.32 |

Reward hacking 탐지 (플래그 에피소드 비율)

| policy | set | idle_forever | shadowing | attack_spam | water_farming | boundary_hugging | chase_to_death | suspected |
|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| random | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| ppo_v0_s0 | eval_seen_map | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | idle_forever |
| ppo_v0_s1 | eval_seen_map | 0.70 | 0.00 | 0.00 | 0.20 | 0.00 | 0.00 | idle_forever |
| ppo_v0_s2 | eval_seen_map | 0.60 | 0.00 | 0.00 | 0.25 | 0.00 | 0.00 | idle_forever |
