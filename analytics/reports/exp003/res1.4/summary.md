| policy | set | n | survival | kills | hunt success | energy/kill | invalid atk | give-ups | death rate |
|---|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map@res1.4 | 20 | 2000 ± 0 | 2.05 ± 0.22 | 0.13 ± 0.04 | 106 ± 36 | 0.53 ± 0.14 | 2.9 ± 1.3 | 0.00 |
| random | eval_seen_map@res1.4 | 20 | 1701 ± 97 | 0.10 ± 0.30 | 0.02 ± 0.06 | 139 ± 7 | 0.99 ± 0.01 | 205.9 ± 31.0 | 1.00 |
| ppo_v1_s0 | eval_seen_map@res1.4 | 20 | 1565 ± 130 | 5.60 ± 1.66 | 0.14 ± 0.03 | 60 ± 10 | 0.08 ± 0.09 | 0.0 ± 0.0 | 0.90 |
| ppo_v1_s1 | eval_seen_map@res1.4 | 20 | 1613 ± 190 | 5.05 ± 1.86 | 0.14 ± 0.03 | 55 ± 11 | 0.07 ± 0.06 | 0.0 ± 0.0 | 0.95 |
| ppo_v1_s2 | eval_seen_map@res1.4 | 20 | 1569 ± 170 | 5.85 ± 1.85 | 0.15 ± 0.02 | 54 ± 8 | 0.01 ± 0.02 | 0.0 ± 0.0 | 0.70 |
| ppo_v2_s0 | eval_seen_map@res1.4 | 20 | 1847 ± 276 | 4.60 ± 2.08 | 0.14 ± 0.03 | 60 ± 17 | 0.06 ± 0.08 | 0.0 ± 0.0 | 0.20 |
| ppo_v2_s1 | eval_seen_map@res1.4 | 20 | 1854 ± 211 | 6.45 ± 1.83 | 0.15 ± 0.04 | 61 ± 12 | 0.04 ± 0.07 | 0.0 ± 0.0 | 0.10 |
| ppo_v2_s2 | eval_seen_map@res1.4 | 20 | 1781 ± 242 | 6.50 ± 1.80 | 0.14 ± 0.03 | 60 ± 15 | 0.03 ± 0.06 | 0.0 ± 0.0 | 0.15 |

행동 분포 (비율)

| policy | set | SEARCH | APPROACH | CHASE | ATTACK | GO_TO_WATER | REST | GIVE_UP |
|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map@res1.4 | 0.14 | 0.05 | 0.16 | 0.02 | 0.05 | 0.58 | 0.00 |
| random | eval_seen_map@res1.4 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 |
| ppo_v1_s0 | eval_seen_map@res1.4 | 0.07 | 0.13 | 0.34 | 0.03 | 0.00 | 0.43 | 0.00 |
| ppo_v1_s1 | eval_seen_map@res1.4 | 0.09 | 0.02 | 0.25 | 0.02 | 0.00 | 0.61 | 0.00 |
| ppo_v1_s2 | eval_seen_map@res1.4 | 0.02 | 0.17 | 0.37 | 0.03 | 0.00 | 0.40 | 0.00 |
| ppo_v2_s0 | eval_seen_map@res1.4 | 0.02 | 0.11 | 0.23 | 0.02 | 0.37 | 0.26 | 0.00 |
| ppo_v2_s1 | eval_seen_map@res1.4 | 0.03 | 0.13 | 0.39 | 0.03 | 0.17 | 0.25 | 0.00 |
| ppo_v2_s2 | eval_seen_map@res1.4 | 0.02 | 0.03 | 0.47 | 0.03 | 0.21 | 0.24 | 0.00 |

Reward hacking 탐지 (플래그 에피소드 비율)

| policy | set | idle_forever | shadowing | attack_spam | water_farming | boundary_hugging | chase_to_death | dehydration_neglect | suspected |
|---|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map@res1.4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| random | eval_seen_map@res1.4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| ppo_v1_s0 | eval_seen_map@res1.4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.90 | dehydration_neglect |
| ppo_v1_s1 | eval_seen_map@res1.4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.95 | dehydration_neglect |
| ppo_v1_s2 | eval_seen_map@res1.4 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.70 | dehydration_neglect |
| ppo_v2_s0 | eval_seen_map@res1.4 | 0.00 | 0.00 | 0.00 | 0.30 | 0.00 | 0.00 | 0.10 | water_farming |
| ppo_v2_s1 | eval_seen_map@res1.4 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.05 | - |
| ppo_v2_s2 | eval_seen_map@res1.4 | 0.00 | 0.00 | 0.00 | 0.05 | 0.00 | 0.00 | 0.05 | - |
