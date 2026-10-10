| policy | set | n | survival | kills | hunt success | energy/kill | invalid atk | give-ups | death rate |
|---|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map | 20 | 2000 ± 0 | 2.10 ± 0.44 | 0.12 ± 0.05 | 127 ± 58 | 0.56 ± 0.14 | 3.2 ± 1.7 | 0.00 |
| rule | eval_unseen_map | 20 | 2000 ± 0 | 2.25 ± 0.43 | 0.14 ± 0.06 | 91 ± 42 | 0.44 ± 0.16 | 2.2 ± 1.2 | 0.00 |
| random | eval_seen_map | 20 | 1763 ± 143 | 0.20 ± 0.40 | 0.04 ± 0.07 | 172 ± 16 | 0.99 ± 0.01 | 211.9 ± 41.0 | 0.80 |
| random | eval_unseen_map | 20 | 1734 ± 119 | 0.10 ± 0.30 | 0.02 ± 0.07 | 207 ± 10 | 0.99 ± 0.01 | 210.8 ± 55.7 | 0.90 |
| ppo_v1_s0 | eval_seen_map | 20 | 1608 ± 162 | 5.90 ± 1.67 | 0.15 ± 0.03 | 57 ± 9 | 0.06 ± 0.10 | 0.0 ± 0.0 | 0.80 |
| ppo_v1_s0 | eval_unseen_map | 20 | 1491 ± 220 | 6.60 ± 1.39 | 0.15 ± 0.03 | 56 ± 13 | 0.07 ± 0.09 | 0.0 ± 0.0 | 0.65 |
| ppo_v1_s1 | eval_seen_map | 20 | 1714 ± 141 | 5.10 ± 1.58 | 0.14 ± 0.03 | 52 ± 8 | 0.10 ± 0.12 | 0.0 ± 0.0 | 1.00 |
| ppo_v1_s1 | eval_unseen_map | 20 | 1607 ± 189 | 5.05 ± 1.77 | 0.15 ± 0.04 | 59 ± 21 | 0.11 ± 0.10 | 0.0 ± 0.0 | 0.90 |
| ppo_v1_s2 | eval_seen_map | 20 | 1638 ± 136 | 5.20 ± 1.78 | 0.15 ± 0.04 | 56 ± 11 | 0.01 ± 0.03 | 0.0 ± 0.0 | 0.90 |
| ppo_v1_s2 | eval_unseen_map | 20 | 1592 ± 192 | 5.90 ± 1.14 | 0.15 ± 0.03 | 56 ± 12 | 0.03 ± 0.05 | 0.0 ± 0.0 | 0.90 |
| ppo_v2_s0 | eval_seen_map | 20 | 1882 ± 252 | 5.45 ± 1.86 | 0.14 ± 0.03 | 56 ± 10 | 0.12 ± 0.13 | 0.0 ± 0.0 | 0.10 |
| ppo_v2_s0 | eval_unseen_map | 20 | 1776 ± 244 | 4.75 ± 2.47 | 0.14 ± 0.05 | 60 ± 25 | 0.06 ± 0.06 | 0.0 ± 0.0 | 0.25 |
| ppo_v2_s1 | eval_seen_map | 20 | 1749 ± 251 | 7.05 ± 0.97 | 0.15 ± 0.02 | 57 ± 7 | 0.02 ± 0.02 | 0.0 ± 0.0 | 0.20 |
| ppo_v2_s1 | eval_unseen_map | 20 | 1756 ± 298 | 7.15 ± 1.06 | 0.15 ± 0.03 | 58 ± 11 | 0.02 ± 0.04 | 0.0 ± 0.0 | 0.05 |
| ppo_v2_s2 | eval_seen_map | 20 | 1717 ± 316 | 6.55 ± 1.43 | 0.14 ± 0.02 | 57 ± 10 | 0.03 ± 0.05 | 0.0 ± 0.0 | 0.15 |
| ppo_v2_s2 | eval_unseen_map | 20 | 1746 ± 308 | 6.35 ± 1.82 | 0.15 ± 0.04 | 60 ± 16 | 0.04 ± 0.07 | 0.0 ± 0.0 | 0.10 |

행동 분포 (비율)

| policy | set | SEARCH | APPROACH | CHASE | ATTACK | GO_TO_WATER | REST | GIVE_UP |
|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map | 0.11 | 0.06 | 0.19 | 0.02 | 0.05 | 0.56 | 0.00 |
| rule | eval_unseen_map | 0.09 | 0.04 | 0.14 | 0.02 | 0.06 | 0.65 | 0.00 |
| random | eval_seen_map | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 |
| random | eval_unseen_map | 0.14 | 0.15 | 0.15 | 0.14 | 0.14 | 0.14 | 0.14 |
| ppo_v1_s0 | eval_seen_map | 0.15 | 0.13 | 0.33 | 0.03 | 0.00 | 0.37 | 0.00 |
| ppo_v1_s0 | eval_unseen_map | 0.09 | 0.11 | 0.39 | 0.03 | 0.00 | 0.37 | 0.00 |
| ppo_v1_s1 | eval_seen_map | 0.07 | 0.02 | 0.23 | 0.02 | 0.00 | 0.65 | 0.00 |
| ppo_v1_s1 | eval_unseen_map | 0.08 | 0.03 | 0.27 | 0.03 | 0.00 | 0.60 | 0.00 |
| ppo_v1_s2 | eval_seen_map | 0.02 | 0.19 | 0.33 | 0.02 | 0.00 | 0.44 | 0.00 |
| ppo_v1_s2 | eval_unseen_map | 0.02 | 0.13 | 0.39 | 0.03 | 0.00 | 0.43 | 0.00 |
| ppo_v2_s0 | eval_seen_map | 0.02 | 0.13 | 0.25 | 0.02 | 0.29 | 0.30 | 0.00 |
| ppo_v2_s0 | eval_unseen_map | 0.02 | 0.11 | 0.23 | 0.02 | 0.35 | 0.26 | 0.00 |
| ppo_v2_s1 | eval_seen_map | 0.03 | 0.13 | 0.41 | 0.03 | 0.13 | 0.27 | 0.00 |
| ppo_v2_s1 | eval_unseen_map | 0.03 | 0.10 | 0.43 | 0.03 | 0.12 | 0.28 | 0.00 |
| ppo_v2_s2 | eval_seen_map | 0.02 | 0.02 | 0.44 | 0.03 | 0.23 | 0.25 | 0.00 |
| ppo_v2_s2 | eval_unseen_map | 0.02 | 0.03 | 0.47 | 0.03 | 0.20 | 0.25 | 0.00 |

Reward hacking 탐지 (플래그 에피소드 비율)

| policy | set | idle_forever | shadowing | attack_spam | water_farming | boundary_hugging | chase_to_death | dehydration_neglect | suspected |
|---|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| rule | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| random | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| random | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| ppo_v1_s0 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.80 | dehydration_neglect |
| ppo_v1_s0 | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.65 | dehydration_neglect |
| ppo_v1_s1 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | dehydration_neglect |
| ppo_v1_s1 | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.90 | dehydration_neglect |
| ppo_v1_s2 | eval_seen_map | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.90 | dehydration_neglect |
| ppo_v1_s2 | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.90 | dehydration_neglect |
| ppo_v2_s0 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.25 | 0.00 | 0.00 | 0.05 | - |
| ppo_v2_s0 | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.35 | 0.00 | 0.00 | 0.10 | water_farming |
| ppo_v2_s1 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.10 | - |
| ppo_v2_s1 | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| ppo_v2_s2 | eval_seen_map | 0.00 | 0.00 | 0.00 | 0.05 | 0.00 | 0.00 | 0.05 | - |
| ppo_v2_s2 | eval_unseen_map | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.10 | - |
