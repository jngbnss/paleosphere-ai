# Environment Spec

코드 기준 확정 스펙. 근거는 [`office-hours.md`](office-hours.md), 수치는 `configs/`.

## 1. 월드

| 항목 | 값 | 위치 |
|---|---|---|
| 좌표 | 2D 연속 `(x, z)`, 0 ≤ x, z ≤ 64 | `configs/world/default.yaml` `map.size` |
| tick | 고정. 렌더링·FPS와 무관 | `core/world.py` |
| 낮/밤 | 400 tick 주기, 마지막 30%가 밤. 밤 시야 ×0.6 | `time` |
| 개체 | 포식자 1, 초식 8 | `population` |
| 자원 | 식물 패치 10 (map_b 6), 물 2, 바위 6 | `map` |
| 번식 | 없음 | — |

### tick 순서 (`World.step`)
0. (외부) 각 정책이 현재 상태로 행동 결정
1. 결정 적용: GIVE_UP 처리, 추격 tick 카운트
2. 이동: 조향 → 바위 밀어내기 → 경계 clip. 질주 여부 기록
3. 공격 → 섭식 → 음수
4. 대사 (에너지·배고픔·갈증·체력), 사망 판정
5. 식물 재생
6. tick +1, 낮/밤 갱신, 포식자 목표 갱신

### 결정성
- `SeedSequence(seed).spawn(3)` → 배치 / 이동(배회 지점) / 전투(명중) Generator 분리
- 개체 순회는 `agent_id` 정렬
- `World.snapshot_hash()` = 스냅샷 JSON(소수 6자리)의 sha256
- 회귀 seed 42·777·2026 결과를 `simulator/tests/golden/`에 고정

## 2. 개체 상태 (`entities/dino.py`)
`health, energy, hunger, thirst` ∈ [0, 100]. hunger·thirst는 높을수록 나쁨.

| 규칙 | 값 (포식자 / 초식) |
|---|---|
| 걷기 / 질주 속도 (m/tick) | 0.35, 0.95 / 0.30, 0.80 |
| 시야 | 18 / 14 |
| 배고픔 증가 / tick | 0.04 / 0.05 |
| 갈증 증가 / tick (+질주 추가) | 0.05 (+0.05) / 0.05 (+0.04) |
| 휴식 회복 / 걷기 / 질주 에너지 | +0.5 / −0.05 / −0.5 · +0.5 / −0.03 / −0.25 |
| hunger 또는 thirst = 100 | 체력 −0.2 / −0.25 per tick |
| energy = 0 | 체력 −0.3 per tick |
| 질주 최소 에너지 | 5 |

사망 원인: `predation`, `starvation`, `dehydration`, `exhaustion` (그 tick 가장 큰 피해 원인).

## 3. 전투 (`combat/attack.py`)
| 항목 | 값 |
|---|---|
| 사거리 | 1.8 |
| 쿨다운 | 6 tick |
| 공격 에너지 | 2 |
| 피해 | 50 (초식 체력 100 → 2회 명중 시 사냥) |
| 명중률 | 걷는 먹잇감 0.75 / 질주 중 0.45 |
| 사냥 성공 시 | 포식자 hunger −60, energy +20 |
| 무효 공격 | 목표 없음 / 사거리 밖 / 쿨다운 중 → `attack_invalid` 이벤트 |
| GIVE_UP | 현재 목표를 30 tick 동안 무시 |

## 4. 포식자 행동 공간 — `Discrete(7)`
| id | 행동 | 시뮬레이터 동작 |
|---|---|---|
| 0 | SEARCH | 맵 내 무작위 지점으로 걷기 |
| 1 | APPROACH | 목표 쪽으로 걷기 (목표 없으면 SEARCH) |
| 2 | CHASE | 목표 쪽으로 질주 (에너지 < 5면 걷기) |
| 3 | ATTACK | 사거리 밖이면 걸어서 접근, 공격 판정 |
| 4 | GO_TO_WATER | 가장 가까운 물로 이동, 물 안이면 마심 |
| 5 | REST | 정지, 에너지 회복 |
| 6 | GIVE_UP | 정지, 목표 포기 |

초식 행동 (`HerbivoreAction`, 학습 대상 아님): WANDER, FLEE, GO_TO_FOOD, GO_TO_WATER, REST.

## 5. 포식자 관찰 공간 — `Box(-1, 1, (26,), float32)`
`policies/observation.py`의 `OBS_FIELDS`가 기준. 규칙 기반 포식자도 같은 `PredatorView`만 사용한다.

| idx | 필드 | 정규화 |
|---|---|---|
| 0 | energy | /100 |
| 1 | hunger | /100 |
| 2 | thirst | /100 |
| 3 | health | /100 |
| 4 | speed | /질주 속도 |
| 5 | prey_visible | 0/1 (목표 존재) |
| 6 | prey_distance | /현재 시야, 없으면 1 |
| 7–8 | prey_dir cos, sin | 없으면 0 |
| 9–10 | prey 상대 속도 x, z | /질주 속도 |
| 11 | prey energy | /100 |
| 12 | 가장 가까운 물 가장자리까지 거리 | /맵 대각선 |
| 13–14 | 물 방향 cos, sin | |
| 15 | 가장 가까운 바위 근접도 | 1 − 거리/5, clip 0 |
| 16 | chase_ticks | /80, clip |
| 17 | attack_cooldown | /6 |
| 18 | is_night | 0/1 |
| 19–25 | 직전 행동 one-hot | 0/1 |

포식자가 모르는 정보(시야 밖 개체, 식물 위치, 다른 초식의 상태)는 넣지 않는다.

## 6. Gymnasium 환경
Phase 2에서 확정 (`PaleoSpherePredator-v0`).
