# Experiments

형식: 가설 → 환경 버전 → 정책 버전 → 보상 설정 → 학습 seed → 평가 seed → 기준선 → 결과 → 실패 원인 → 다음 실험.
수치는 `analytics/reports/<exp>/`의 CSV에서 재현 가능하다. 모델 체크포인트는 Git에 올리지 않는다
(`training/checkpoints/`, 재현 명령은 각 실험에 기록).

---

## Experiment 001 — PPO v0 vs Rule vs Random

| 항목 | 내용 |
|---|---|
| 가설 | 같은 관찰·행동 공간에서 PPO가 보상 v0만으로 규칙 기반 포식자보다 사냥을 더 잘한다 |
| 환경 | `PaleoSpherePredator-v0`, map_a, 포식자 1 · 초식 8 (규칙 기반), max 2000 tick |
| 정책 | `ppo_v0_s{0,1,2}` — PPO MLP [64, 64], 500k step (`configs/training/ppo_v0.yaml`) |
| 보상 | `configs/rewards/v0.yaml` (사냥 +10, potential shaping coef 0.5 · γ 0.99, 이동·질주 비용, 무효 공격 −0.1, 사망 −10) |
| 학습 seed | 0, 1, 2 (에피소드 seed는 [0, 10000)에서 추출) |
| 평가 seed | `eval_seen_map` 10000–10019 (20개, 학습에 사용 안 함) |
| 기준선 | RuleBasedPredator, RandomPolicy |
| 재현 | `uv run python -m training.scripts.train_ppo --seed {0,1,2}` → `uv run python -m training.evaluation.evaluate --policies rule random ppo_v0_s0=ppo:training/checkpoints/ppo_v0_s0/best_model.zip ... --sets eval_seen_map --out analytics/reports/exp001` |

### 결과 (20 seed, 평균 ± 표준편차)

| policy | survival (tick) | kills | hunt success | invalid attack rate | 포식자 사망률 |
|---|---|---|---|---|---|
| rule | 2000 ± 0 | **2.10 ± 0.44** | 0.12 ± 0.05 | 0.56 ± 0.14 | 0.00 |
| random | 1763 ± 143 | 0.20 ± 0.40 | 0.04 ± 0.07 | 0.99 ± 0.01 | 0.80 |
| ppo_v0_s0 | 1655 ± 78 | 0.00 | 0.00 | – | 1.00 |
| ppo_v0_s1 | 1675 ± 64 | 0.00 | 0.00 | – | 0.95 |
| ppo_v0_s2 | 1687 ± 89 | 0.00 | 0.00 | – | 0.95 |

행동 분포

| policy | SEARCH | APPROACH | CHASE | ATTACK | GO_TO_WATER | REST | GIVE_UP |
|---|---|---|---|---|---|---|---|
| rule | 0.11 | 0.06 | 0.19 | 0.02 | 0.05 | 0.56 | 0.00 |
| ppo_v0_s0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.01 | 0.18 | **0.80** |
| ppo_v0_s1 | 0.00 | 0.00 | 0.00 | 0.00 | 0.21 | 0.00 | **0.79** |
| ppo_v0_s2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.25 | 0.43 | 0.32 |

Reward hacking 탐지 (플래그 에피소드 비율): `idle_forever` s0 1.00 · s1 0.70 · s2 0.60 → 3개 seed 모두 **idle_forever**.

### 결론
**가설 기각.** PPO v0는 3개 seed 모두 사냥 0회, 굶어 죽음. 보상 총점은 학습 중 개선됐지만(−51 → −35) 실제 행동은
"제자리에 서서(GIVE_UP·REST) 굶어 죽기"였다. 보상 총점만 봤다면 개선으로 오판했을 것이다.

### 실패 원인 (상세: [`reward-design.md`](reward-design.md))
1. **탐색 실패**: 학습 중 사냥·명중이 단 한 번도 없었다 (TensorBoard `episode/kills` 전 구간 0). 에피소드가 길어(~1,700 tick)
   500k step에 에피소드가 약 300개뿐이고, 사냥에는 약 40 tick 연속 추격이 필요해 무작위 탐색으로는 도달하지 못한다.
2. **shaping 근접 세금**: Φ ≥ 0, γ = 0.99인 shaping은 매 tick (γ−1)·Φ ≤ 0을 준다. 먹잇감을 목표로 잡고 있으면 손해이고
   GIVE_UP으로 목표를 버리면 Φ = 0이 되어 손해가 사라진다 → **GIVE_UP 80%의 직접 원인**.
3. **탐지기 사각지대**: 초기 idle 탐지기는 REST 비율만 봐서 GIVE_UP 정지를 놓쳤다 → REST + GIVE_UP 기준으로 수정.

### 다음 실험
Experiment 002: 보상 v1 (shaping γ = 1, 명중 보상, 배고픔 비례 비용, 목표 없는 GIVE_UP 비용)
+ 학습 커리큘럼(일부 에피소드를 먹잇감 근처에서 시작) + 규칙 기반 시연으로 행동 복제(BC) 사전학습 후 PPO.

---

## Experiment 002 — 보상 v1 + BC 사전학습 + 커리큘럼

| 항목 | 내용 |
|---|---|
| 가설 | 보상 누수를 고치고(shaping γ=1) 탐색 문제를 BC 사전학습으로 우회하면, PPO가 교사인 규칙 기반 정책보다 사냥을 더 잘하고 처음 보는 환경에서도 유지된다 |
| 환경 | `PaleoSpherePredator-v0`, 학습 map_a. 학습 에피소드 30%는 먹잇감 5–9m에서 시작 (평가는 항상 기본 배치) |
| 정책 | `ppo_v1_s{0,1,2}` — 규칙 기반 시연 40 에피소드로 BC(모방 정확도 98%) → PPO 500k step, lr 1e-4, ent 0.02 (`configs/training/ppo_v1.yaml`) |
| 보상 | `configs/rewards/v1.yaml` (변경점은 [`reward-design.md`](reward-design.md)) |
| 학습 seed | 0, 1, 2 |
| 평가 seed | eval_seen_map 10000–10019 (map_a), eval_unseen_map 20000–20019 (map_b: 물 위치 이동·식물 −40%), 자원 ×0.6 / ×1.4 (map_a) |
| 기준선 | RuleBasedPredator, RandomPolicy, PPO v0 |
| 모델 | 체크포인트 선택에 쓴 seed(10000–10004)와 평가 seed가 겹치므로 **선택 없이 `final_model.zip`으로 평가** |
| 재현 | `uv run python -m training.scripts.train_ppo --config ppo_v1 --seed {0,1,2}` → `evaluate --sets eval_seen_map eval_unseen_map [--resource-scale 0.6/1.4] --out analytics/reports/exp002/...` |

### 결과 (각 20 seed, 평균 ± 표준편차)

| policy | set | kills | hunt success | energy/kill | invalid attack rate | survival | 포식자 사망률 |
|---|---|---|---|---|---|---|---|
| rule | seen | 2.10 ± 0.44 | 0.12 | 127 | 0.56 | 2000 | 0.00 |
| rule | **unseen map_b** | 2.25 ± 0.43 | 0.14 | 91 | 0.44 | 2000 | 0.00 |
| ppo_v0 (3 seed) | seen | 0.00 | – | – | – | 1655–1687 | 0.95–1.00 |
| ppo_v1_s0 | seen | **5.90 ± 1.67** | 0.15 | 57 | 0.06 | 1608 | 0.80 |
| ppo_v1_s0 | **unseen map_b** | **6.60 ± 1.39** | 0.15 | 56 | 0.07 | 1491 | 0.65 |
| ppo_v1_s1 | seen | 5.10 ± 1.58 | 0.14 | 52 | 0.10 | 1714 | 1.00 |
| ppo_v1_s1 | unseen map_b | 5.05 ± 1.77 | 0.15 | 59 | 0.11 | 1607 | 0.90 |
| ppo_v1_s2 | seen | 5.20 ± 1.78 | 0.15 | 56 | 0.01 | 1638 | 0.90 |
| ppo_v1_s2 | unseen map_b | 5.90 ± 1.14 | 0.15 | 56 | 0.03 | 1592 | 0.90 |

자원 변화 (map_a, 20 seed): 식물 ×0.6 — rule 1.95 / v1 4.90–6.35 사냥, ×1.4 — rule 2.05 / v1 5.05–5.85 사냥.

행동 분포 (seen): rule REST 0.56 · CHASE 0.19 · ATTACK 0.02 / v1 CHASE 0.23–0.33 · REST 0.37–0.65 · ATTACK 0.02–0.03 · **GO_TO_WATER 0.00**.

### 결론
- **사냥 측면 가설 채택.** 3개 학습 seed 모두 규칙 기반보다 사냥 2.4–3.1배, 사냥당 에너지 절반 이하, 무효 공격 비율 0.56 → 0.01–0.11.
  처음 보는 seed·처음 보는 자원 배치(map_b)·자원량 ±40%에서도 같은 수준 유지.
  교사(규칙 기반)를 모방한 뒤 PPO가 "사거리 경계에서 공격하지 말고 붙을 때까지 추격" 같은 개선을 스스로 찾았다.
- **생존 측면 가설 기각.** 포식자 사망률 65–100%, 사망 원인 거의 전부 **탈수** (평균 갈증 ~70). GO_TO_WATER를 한 번도 고르지 않는다.
  보상 총점·사냥 수만 봤다면 성공으로 오판했을 결과.

### 실패 원인
1. 탈수 사망은 ~1,600 tick 뒤에 오는데 γ = 0.99에서 −10 사망 페널티는 사실상 보이지 않는다 (0.99^1000 ≈ 4e−5).
2. 배고픔은 매 tick 비용(hunger_penalty)이 있지만 갈증에는 없다 → 비대칭.
3. drink_reward 0.05는 이동 비용·기회비용 대비 작다.
4. 탐지기 6종이 이 유형을 잡지 못했다 → `dehydration_neglect`(탈수 사망 + 물 행동 ≤ 1%) 추가, Exp 002 보고서 재계산.

### 다음 실험
Experiment 003: 보상 v2 — `thirst_penalty` −0.01·thirst/100 (hunger와 대칭), drink_reward 0.05 → 0.2. 나머지 동일.

---

## Experiment 003 — 보상 v2 (갈증 비례 비용)

| 항목 | 내용 |
|---|---|
| 가설 | 갈증에도 매 tick 비용을 주면(배고픔과 대칭) 사냥 능력을 유지하면서 탈수 사망이 사라진다 |
| 환경·학습 방법 | Experiment 002와 동일 (BC 사전학습 + 커리큘럼 30%, 500k step) — 보상만 변경 |
| 정책 | `ppo_v2_s{0,1,2}` (`configs/training/ppo_v2.yaml`) |
| 보상 | `configs/rewards/v2.yaml` = v1 + `thirst_penalty_coef` 0.01, drink_reward 0.05 → 0.2 |
| 평가 | Exp 002와 같은 세트, `final_model.zip` |
| 재현 | `train_ppo --config ppo_v2 --seed {0,1,2}` → `evaluate ... --out analytics/reports/exp003/...` |

### 결과 (각 20 seed)

| policy | set | kills | invalid attack rate | energy/kill | 포식자 사망률 | GO_TO_WATER | 평균 갈증 |
|---|---|---|---|---|---|---|---|
| rule | seen / map_b | 2.10 / 2.25 | 0.56 / 0.44 | 127 / 91 | 0.00 / 0.00 | 0.05 | – |
| ppo_v1 (3 seed) | seen | 5.10–5.90 | 0.01–0.10 | 52–57 | **0.80–1.00** | 0.00 | ~70 |
| ppo_v2_s0 | seen / map_b | 5.45 / 4.75 | 0.12 / 0.06 | 56 / 60 | 0.10 / 0.25 | 0.29 | 36 |
| ppo_v2_s1 | seen / map_b | **7.05 / 7.15** | 0.02 / 0.02 | 57 / 58 | 0.20 / **0.05** | 0.13 | 52 |
| ppo_v2_s2 | seen / map_b | 6.55 / 6.35 | 0.03 / 0.04 | 57 / 60 | 0.15 / 0.10 | 0.23 | 46 |

자원 변화 (식물 ×0.6 / ×1.4): v2 사냥 4.90–7.00 / 4.60–6.50, 사망률 0.10–0.15 / 0.10–0.20. Rule 1.95 / 2.05.

주의: 생존 tick 평균이 2000보다 작은 것은 사망뿐 아니라 **초식 전멸로 에피소드가 일찍 끝난 경우**를 포함한다 (사냥 7회 이상).
생존 판단은 포식자 사망률로 한다.

### 결론
- **가설 채택.** 탈수 사망률 0.65–1.00 → 0.05–0.25. 사냥은 v1 수준 이상 유지 (seed 1·2는 증가).
- 3개 학습 seed 모두 Rule 대비 사냥 2.1–3.4배, 무효 공격 비율 1/5 이하, 처음 보는 맵·자원량에서도 유지.
- Rule은 여전히 사망률 0으로 가장 안정적이다. PPO는 더 공격적이고 효율적이지만 일부 에피소드에서 죽는다 — 트레이드오프.

### 남은 문제
- `ppo_v2_s0`: map_b에서 `water_farming` 플래그 35% (물 행동 32%, 평균 갈증 36). drink_reward 0.2가 다소 크다.
- 학습 seed 간 편차가 크다 (사망률 0.05–0.25). 더 긴 학습 또는 seed 5개 이상 필요.

### 다음 실험 후보
drink_reward 0.2 → 0.1로 낮춰 물가 머무름 확인, γ 0.995로 장기 생존 신호 강화, 초식공룡 학습(다중 에이전트)은 MVP 이후.
