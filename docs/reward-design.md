# Reward Design

포식자 보상은 component별로 계산·기록한다 (`training/rewards/predator_reward.py`, `info["reward_components"]`).
정책 평가는 보상 총점이 아니라 사냥·생존·행동 분포·hacking 탐지 결과로 한다.

## v0 (`configs/rewards/v0.yaml`)

| component | 값 | 의도 |
|---|---|---|
| hunt_reward | +10 / 사냥 | 핵심 목표 |
| distance_reward | γΦ(s′) − Φ(s), Φ = 0.5·(1 − d/vision), γ = 0.99 | 먹잇감 접근 유도 (potential-based) |
| move / sprint | −0.002 / −0.005 per tick | 무의미한 이동 억제 |
| long_chase | −0.01 per tick (추격 > 60 tick) | 무리한 추격 억제 |
| invalid_attack | −0.1 | 사거리 밖·쿨다운 공격 억제 |
| energy | −0.02 per tick (energy < 10) | 탈진 회피 |
| drink | +0.05 (갈증 > 50일 때만) | 물가 파밍 방지 |
| survival | 0 | 정지 정책 방지 목적으로 꺼 둠 |
| death | −10 | |

## v0 분석 — Experiment 001

**관찰**: 3개 학습 seed 모두 사냥 0, 행동의 80%가 GIVE_UP (s0, s1). `idle_forever` 탐지.

### 원인 1 — shaping 근접 세금 (설계 실수)
potential-based shaping의 한 step 값은 γΦ(s′) − Φ(s). 제자리에 있으면 (γ − 1)·Φ(s)이다.
- Φ ≥ 0, γ = 0.99 → 먹잇감을 목표로 잡고 있는 매 tick마다 최대 −0.005 (coef 0.5).
- 학습 중 `reward/distance_reward`가 에피소드당 약 −1 ~ −3 (coef 1.0으로 올린 시험에서는 −8).
- GIVE_UP은 목표를 지워 Φ = 0으로 만들어 이 세금을 없앤다. **GIVE_UP 80%는 이 세금을 최적화한 결과.**
- 처음 설계 때 Φ ≤ 0 버전(−d/vision)의 반대 문제(제자리에서 +(1−γ)|Φ|)를 테스트로 발견해 Φ ≥ 0으로 바꿨는데
  (D-010), 부호만 뒤집혀 같은 누수가 "근접 회피" 쪽으로 나타났다.

**수정 (v1)**: shaping γ = 1.0. 한 step은 Φ(s′) − Φ(s)이고 에피소드 합은 Φ(끝) − Φ(시작)으로 telescoping되어
제자리·왕복으로 얻거나 잃는 값이 정확히 0이다 (테스트: `test_shaping_is_potential_based`).

### 원인 2 — 탐색 실패
- 학습 전 구간에서 명중·사냥 0회 (`episode/kills`, `reward/hunt_reward` 모두 0).
- 사냥 = 약 40 tick 연속 CHASE 후 사거리 1.8 이내 ATTACK. 무작위 정책(Random)은 20 seed 평균 0.2회.
- 에피소드 ~1,700 tick → 500k step에 에피소드 약 300개. 보상 신호가 거의 없다.
- 단순 스크립트("목표가 있으면 CHASE, 1.2m 이내면 ATTACK")는 사냥 1~5회 → **행동 공간으로 해는 존재**, 문제는 탐색.

**수정 (v1 + 학습 방법)**
| 변경 | 이유 |
|---|---|
| `hit_reward` +2 / 명중 (신규) | 사냥(명중 2회)까지 중간 신호. 명중은 쿨다운과 먹잇감 사망으로 상한이 있어 파밍 불가 |
| `hunger_penalty` −0.01·hunger/100 per tick (신규) | 굶는 비용을 매 tick 체감. 정지 정책이 더는 공짜가 아님 |
| `idle_penalty` −0.05 (목표 없는데 GIVE_UP, 신규) | GIVE_UP을 "정지 버튼"으로 쓰는 우회로 차단 |
| move / sprint −0.001 / −0.003 | 탐색 비용 완화 |
| shaping coef 0.5 → 1.0 | γ = 1이라 최적 정책 불변, 신호만 강화 |
| 커리큘럼: 학습 에피소드 30%를 먹잇감 5–9m에서 시작 | 추격 경험 밀도 증가. **평가는 항상 기본 배치** |
| BC 사전학습: 규칙 기반 시연 40 에피소드(학습 seed)로 actor·critic 초기화, PPO lr 1e-4 | 탐색 문제 우회. PPO가 교사(Rule)를 넘어서는지가 평가 기준 |

보상만 바꾸고 BC 없이 200k step 학습한 시험(v1 + 커리큘럼)에서도 명중 0회 → BC 없이는 탐색이 해결되지 않음을 확인.

### 원인 3 — 탐지기 사각지대
초기 `idle_forever`는 REST 비율만 봤다. GIVE_UP도 제자리 정지이므로 v0 정책을 놓쳤다.
→ `stationary = REST + GIVE_UP`으로 수정, 회귀 테스트 `test_idle_via_give_up_synthetic` 추가.

## v1 (`configs/rewards/v1.yaml`)
v0 대비 변경은 위 표. 결과는 [`experiments.md`](experiments.md) Experiment 002.

## 남은 위험
- BC 교사의 버릇(사거리 경계에서 ATTACK → 무효 공격)을 그대로 물려받을 수 있다 → `invalid_attack_rate`로 추적.
- hunger_penalty가 너무 크면 무리한 추격으로 탈진 사망 → `chase_to_death` 탐지기로 추적.
