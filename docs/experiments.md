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
