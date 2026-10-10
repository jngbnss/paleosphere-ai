| policy | set | n | survival | kills | hunt success | energy/kill | invalid atk | give-ups | death rate |
|---|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map@res0.6 | 20 | 1984 ± 68 | 1.95 ± 0.50 | 0.11 ± 0.05 | 116 ± 41 | 0.54 ± 0.12 | 2.8 ± 1.5 | 0.05 |
| random | eval_seen_map@res0.6 | 20 | 1704 ± 129 | 0.10 ± 0.30 | 0.03 ± 0.08 | 198 ± 7 | 1.00 ± 0.01 | 172.2 ± 73.2 | 0.90 |
| ppo_v1_s0 | eval_seen_map@res0.6 | 20 | 1619 ± 142 | 6.35 ± 1.28 | 0.15 ± 0.03 | 54 ± 7 | 0.06 ± 0.06 | 0.0 ± 0.0 | 0.75 |
| ppo_v1_s1 | eval_seen_map@res0.6 | 20 | 1735 ± 123 | 4.90 ± 1.37 | 0.15 ± 0.04 | 55 ± 12 | 0.07 ± 0.10 | 0.0 ± 0.0 | 1.00 |
| ppo_v1_s2 | eval_seen_map@res0.6 | 20 | 1702 ± 156 | 6.00 ± 1.38 | 0.15 ± 0.04 | 54 ± 8 | 0.02 ± 0.04 | 0.0 ± 0.0 | 0.85 |
| ppo_v2_s0 | eval_seen_map@res0.6 | 20 | 1883 ± 189 | 4.90 ± 2.00 | 0.15 ± 0.04 | 56 ± 15 | 0.11 ± 0.16 | 0.0 ± 0.0 | 0.15 |
| ppo_v2_s1 | eval_seen_map@res0.6 | 20 | 1771 ± 265 | 7.00 ± 1.34 | 0.15 ± 0.03 | 58 ± 8 | 0.03 ± 0.04 | 0.0 ± 0.0 | 0.10 |
| ppo_v2_s2 | eval_seen_map@res0.6 | 20 | 1882 ± 189 | 5.60 ± 2.15 | 0.15 ± 0.03 | 59 ± 11 | 0.03 ± 0.05 | 0.0 ± 0.0 | 0.10 |

행동 분포 (비율)

| policy | set | SEARCH | APPROACH | CHASE | ATTACK | GO_TO_WATER | REST | GIVE_UP |
|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map@res0.6 | 0.17 | 0.05 | 0.17 | 0.02 | 0.05 | 0.53 | 0.00 |
| random | eval_seen_map@res0.6 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 | 0.14 |
| ppo_v1_s0 | eval_seen_map@res0.6 | 0.11 | 0.16 | 0.33 | 0.03 | 0.00 | 0.37 | 0.00 |
| ppo_v1_s1 | eval_seen_map@res0.6 | 0.12 | 0.03 | 0.23 | 0.02 | 0.00 | 0.61 | 0.00 |
| ppo_v1_s2 | eval_seen_map@res0.6 | 0.01 | 0.18 | 0.37 | 0.03 | 0.00 | 0.41 | 0.00 |
| ppo_v2_s0 | eval_seen_map@res0.6 | 0.02 | 0.14 | 0.23 | 0.02 | 0.31 | 0.29 | 0.00 |
| ppo_v2_s1 | eval_seen_map@res0.6 | 0.03 | 0.14 | 0.44 | 0.03 | 0.09 | 0.27 | 0.00 |
| ppo_v2_s2 | eval_seen_map@res0.6 | 0.01 | 0.05 | 0.41 | 0.02 | 0.30 | 0.20 | 0.00 |

Reward hacking 탐지 (플래그 에피소드 비율)

| policy | set | idle_forever | shadowing | attack_spam | water_farming | boundary_hugging | chase_to_death | dehydration_neglect | suspected |
|---|---|---|---|---|---|---|---|---|---|
| rule | eval_seen_map@res0.6 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| random | eval_seen_map@res0.6 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| ppo_v1_s0 | eval_seen_map@res0.6 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.75 | dehydration_neglect |
| ppo_v1_s1 | eval_seen_map@res0.6 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.00 | dehydration_neglect |
| ppo_v1_s2 | eval_seen_map@res0.6 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.85 | dehydration_neglect |
| ppo_v2_s0 | eval_seen_map@res0.6 | 0.00 | 0.05 | 0.00 | 0.40 | 0.00 | 0.00 | 0.15 | water_farming |
| ppo_v2_s1 | eval_seen_map@res0.6 | 0.00 | 0.05 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | - |
| ppo_v2_s2 | eval_seen_map@res0.6 | 0.00 | 0.05 | 0.00 | 0.15 | 0.00 | 0.00 | 0.05 | - |
