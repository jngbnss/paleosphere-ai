# PaleoSphere AI — Office Hours 결과 (2026-10-11)

원본 기획 프롬프트를 검토하고 모든 결정을 **권장안(Recommended)** 으로 확정한 문서다.
이후 구현 프롬프트(`docs/roadmap-prompts.md`)는 이 문서를 스펙으로 삼는다.

---

## 0. Office Hours 핵심 피드백

### 0.1 이 프로젝트의 진짜 가치
"공룡 게임"이 아니라 **"같은 환경에서 규칙 기반 포식자 vs PPO 포식자를 수치로 비교하고, reward hacking을 찾아 고친 기록"** 이다.
데모 한 장면보다 `docs/experiments.md`의 비교표 하나가 더 강한 증거다.
따라서 우선순위는 **시뮬레이션 → 기준선 → RL → 평가 → 시각화** 순서로 고정한다.

### 0.2 범위 축소 (Push-back)
| 원본 기획 | 결정 | 이유 |
|---|---|---|
| 3D Godot 화면 | **2D 탑뷰 Godot** | 3D 에셋/카메라 작업이 AI 증명에 기여하지 않음 |
| Godot이 관찰값을 Python에 보내 행동을 받음 | **Python이 시뮬레이션의 유일한 진실(single source of truth), Godot은 렌더링 + 제어 명령만** | 생태계 규칙을 GDScript에 중복 구현하면 결정성·일관성 붕괴 |
| 낮/밤 또는 날씨 | **낮/밤만** (밤에 시야 ×0.6) | 관찰값 1개로 표현 가능, 구현 저렴 |
| 탐험자 모드 | **MVP 제외** (관찰자 모드만) | 4단계 안에 들어가지 않음 |
| 개체수 시계열 예측 | **MVP 이후** | 번식 없는 MVP에서 의미 있는 시계열이 안 나옴 |
| 번식 | **제외** | 에피소드 단위 평가를 단순하게 유지 |
| PettingZoo / 다중 에이전트 | **MVP 이후** | 원본 기획과 동일 |
| ONNX / Godot 내부 추론 | **MVP 이후** | 원본 기획과 동일 |

### 0.3 반드시 지켜야 할 설계 포인트
1. **포식자가 실제로 굶어 죽을 수 있어야 한다.** 그렇지 않으면 "추격 포기" 판단을 학습할 이유가 없다.
2. **초식공룡이 단거리에서는 포식자보다 느리고, 장거리에서는 지구력이 더 좋아야 한다.** 그래야 "언제 포기할지"가 의미를 가진다.
3. **거리 보상은 potential-based shaping으로만 준다.** (따라가기만 하고 공격 안 하는 hacking 방지)
4. **행동 공간은 매크로 행동(Discrete 7)** 이다. RL은 "무엇을 할지"를 고르고, 이동 조향은 시뮬레이터가 한다. 규칙 기반 정책도 같은 7개 행동 중에서 고른다 → 공정한 비교.

---

## 1. 첫 MVP 공룡 종류
| 역할 | ID | 모티브 | 특징 |
|---|---|---|---|
| 초식 | `herbivore` | 소형 조각류 (드리오사우루스 계열) | 걷기 0.30, 질주 0.80 m/tick, 질주 지구력 높음, 시야 14 |
| 육식 | `predator` | 소형 수각류 (딜로포사우루스 계열) | 걷기 0.35, 질주 0.95 m/tick, 질주 에너지 소모 큼, 시야 18 |

기본 시나리오: 포식자 1, 초식 8, 맵 64×64, 식물 패치 10, 물웅덩이 2, 바위 장애물 6.
모든 수치는 `configs/world/default.yaml`에서 관리한다.

## 2. Core Simulation 상태 모델
- 2D 연속 좌표 `(x, z)`. Godot 2D와 1:1 대응.
- `Dino` (dataclass, slots):
  `agent_id, species, pos[2], vel[2], health, energy, hunger, thirst, age, current_action, target_id, alive, attack_cooldown, chase_ticks, give_up_until, death_cause`
- 수치 범위: health/energy/hunger/thirst 모두 0–100. hunger·thirst는 **높을수록 나쁨**. 100 도달 시 health 감소.
- `PlantPatch(pos, radius, food, max_food, regrow_rate)`, `WaterSource(pos, radius)`, `Rock(pos, radius)`
- `World(config, tick, is_night, dinos, plants, waters, rocks, rng)` — 직렬화 가능한 `to_snapshot()` 제공 (Godot 전송·리플레이용).

## 3. 생태계 tick 처리 방식
- 고정 tick: `dt = 0.25s` 개념값. FPS와 무관.
- **결정성**: `numpy.random.SeedSequence(seed).spawn(n)`으로 하위 시스템별 Generator 분리 (배치·이동 노이즈·전투). 모든 순회는 `agent_id` 정렬 순.
- 한 tick 순서 (고정):
  1. 낮/밤 갱신
  2. 각 개체 관찰 생성
  3. 모든 정책이 **동시에** 행동 결정 (이전 상태 기준)
  4. 이동 적용 (조향 + 장애물·경계 충돌)
  5. 상호작용 해결: 공격 → 섭식 → 음수
  6. 대사: 에너지/배고픔/갈증 갱신
  7. 사망 판정 (원인 기록: starvation / dehydration / predation / exhaustion)
  8. 식물 재생
  9. tick += 1, 로그 기록
- 같은 seed + 같은 config + 같은 정책 → 스냅샷 해시 동일 (테스트로 강제).

## 4. 규칙 기반 정책 (기준선, AI 아님)
수치는 `configs/policies/rule_based.yaml`.

**육식 RuleBasedPredator** (우선순위 순)
1. 갈증 > 70 → GO_TO_WATER
2. 에너지 < 20 → REST
3. 배고픔 < 30 → REST
4. 먹잇감 시야 내 & 추격 tick > 40 → GIVE_UP
5. 먹잇감 거리 ≤ 공격거리 & 쿨다운 0 → ATTACK
6. 먹잇감 거리 ≤ 10 → CHASE
7. 먹잇감 시야 내 → APPROACH
8. 그 외 → SEARCH

**초식 RuleBasedHerbivore**: 포식자 ≤ 10 → FLEE / 갈증 > 60 → 물 / 배고픔 > 50 → 식물 / 에너지 < 20 → REST / 그 외 무리 중심 근처 WANDER.
(초식 행동 공간은 별도 enum, 학습 대상 아님)

## 5. 육식공룡 관찰 공간 — `Box(-1, 1, (26,), float32)`
| idx | 값 | 정규화 |
|---|---|---|
| 0–3 | energy, hunger, thirst, health | /100 |
| 4 | 현재 속도 | /질주속도 |
| 5 | 먹잇감 보임 여부 | 0/1 |
| 6 | 가장 가까운 먹잇감 거리 | /시야, 안 보이면 1 |
| 7–8 | 먹잇감 방향 (cos, sin) | 안 보이면 0 |
| 9–10 | 먹잇감 상대 속도 (x, z) | /질주속도 |
| 11 | 먹잇감 에너지 추정 (지친 정도) | /100 |
| 12 | 가장 가까운 물 거리 | /맵 대각선 |
| 13–14 | 물 방향 (cos, sin) | |
| 15 | 전방 장애물 근접도 | 0–1 |
| 16 | 추격 지속 tick | /max_chase(80), clip |
| 17 | 공격 쿨다운 | /max |
| 18 | 밤 여부 | 0/1 |
| 19–25 | 직전 행동 one-hot (7) | 0/1 |

> 총 26차원. 구현 시 최종 차원은 `environment-spec.md`에 확정 기록. 시뮬레이터가 아는 정보(전체 개체 위치 등)는 넣지 않는다.

## 6. 육식공룡 행동 공간 — `Discrete(7)`
`0 SEARCH, 1 APPROACH(걷기로 접근), 2 CHASE(질주), 3 ATTACK, 4 GO_TO_WATER, 5 REST, 6 GIVE_UP(현재 목표 30 tick 무시)`

## 7. 초기 보상 함수와 예상 reward hacking
`configs/rewards/v0.yaml`, 매 step component별 `info["reward_components"]`에 기록.

| component | 값 | 비고 |
|---|---|---|
| hunt_reward | +10.0 | 사냥 성공 |
| eat_reward | +0.02 / 섭취량 | |
| distance_shaping | γΦ(s') − Φ(s), Φ = −dist/시야 × 0.5 | **potential-based**만 허용 |
| move_penalty | −0.002 / tick (이동 시) | |
| sprint_penalty | −0.005 / tick (CHASE) | |
| long_chase_penalty | −0.01 / tick (chase_ticks > 60) | |
| invalid_attack_penalty | −0.1 | 사거리 밖·쿨다운 중 공격 |
| low_energy_penalty | −0.02 / tick (energy < 10) | |
| drink_reward | +0.05 (thirst > 50일 때 음수) | 갈증 낮을 때는 0 → 물가 파밍 방지 |
| survival_reward | +0.0 (v0에서는 끔) | 켜면 REST 정체 위험 |
| death_penalty | −10.0 | |

**예상 hacking과 탐지 규칙** (`evals/reward-hacking-cases.yaml` + detector 함수)
| 이름 | 탐지 기준 |
|---|---|
| idle_forever | REST 비율 > 70% & 사냥 0 |
| shadowing | APPROACH/CHASE 비율 > 60% & ATTACK < 1% |
| attack_spam | invalid attack 비율 > 50% |
| water_farming | GO_TO_WATER 비율 > 40% & thirst 평균 < 20 |
| boundary_hugging | 경계 2m 이내 체류 > 50% |
| chase_to_death | exhaustion 사망 비율 > 30% |

## 8. Gymnasium 환경 구조
- ID: `PaleoSpherePredator-v0`, `training/environments/predator_env.py`
- 학습 대상 포식자 1마리, 나머지는 `RuleBasedHerbivore`. 다른 포식자 없음.
- `reset(seed)` → World 재생성. `step(action)` → 1 tick (frame_skip 옵션, 기본 1).
- `terminated`: 포식자 사망 **또는** 초식 전멸. `truncated`: `max_steps=2000` 도달.
- `info`: `reward_components`, `kills`, `death_cause`, `action_counts`.
- `check_env` 통과 필수. 벡터화: `SubprocVecEnv` 8개.
- 맵 변형: `map_a`(학습), `map_b`(물 위치 이동 + 식물 −40%, **학습 미사용**).

## 9. Godot ↔ Python 연동
- **Python sim-server (FastAPI + WebSocket)** 가 World를 돌리고 매 tick 스냅샷을 push (기본 10 tick/s, 속도 조절 가능).
- Godot은 수신 스냅샷을 렌더링하고 제어 명령만 보낸다: `start(seed, map, predator_policy)`, `pause`, `resume`, `set_speed`, `select(agent_id)`.
- 별도 `POST /predict` 엔드포인트로 원본 기획의 `{observation} → {action, policy_version, inference_time_ms}` 인터페이스도 제공 (외부 클라이언트·벤치용).
- 메시지 스키마는 Pydantic 모델로 정의하고 JSON Schema를 `docs/protocol.md`에 내보낸다.
- 이점: 생태계 규칙 중복 없음, 리플레이 파일(jsonl)로 오프라인 재생도 같은 렌더러 사용.

## 10. 첫 평가 seed와 시나리오 (`evals/fixed-seeds.yaml`)
| 세트 | seed | 맵 | 목적 |
|---|---|---|---|
| train | 0–9999 랜덤 | map_a | 학습 전용 |
| eval_seen_map | 10000–10019 | map_a | 보지 않은 seed |
| eval_unseen_map | 20000–20019 | map_b | 보지 않은 자원 배치 |
| regression | 42, 777, 2026 | map_a | 결정성·회귀 테스트 |

비교는 학습 seed 3개(0, 1, 2) × 평가 세트 20 seed 이상.

## 11. 규칙 기반 vs PPO 비교 지표
- 생존 tick (평균±표준편차)
- 사냥 수 / 에피소드, 사냥 성공률 (kills / ATTACK 시도)
- 사냥당 에너지 소비
- invalid attack 비율
- 추격 포기 비율, 포기 후 N tick 내 재추격 성공률
- 사망 원인 분포
- 행동 분포 (hacking 탐지 입력)
- Random / RuleBased 대비 개선율
- 시스템: env steps/s, 추론 지연(ms)

## 12. 역할 구분
| 계층 | 책임 | AI 여부 |
|---|---|---|
| Visualizer (Godot) | 렌더링, 카메라, UI, 오버레이 | 아님 |
| Core Simulation | 물리·대사·전투·자원 규칙, 결정성 | 아님 (환경) |
| Rule-based Policy | 기준선 | 아님 (기준선) |
| Gym Env + Reward | 관찰/행동/보상 설계 | **AI 설계** |
| PPO Training/Eval | 학습, 평가, hacking 분석, 일반화 | **AI** |
| Inference/Sim Server | 정책 서빙, 스트리밍 | 인프라 |

## 13. 7인 팀 역할 분담
1. **리드/PM** — 범위 관리, decision-log, 실험 리뷰, 발표 스토리
2. **Sim A** — World/Dino/자원/tick 루프, 결정성
3. **Sim B** — 전투·대사 규칙, 규칙 기반 정책, config 시스템
4. **RL 환경** — Gym env, 관찰/행동 공간, 보상 함수, hacking detector
5. **학습/평가** — PPO 학습, 평가 스크립트, 실험 보고서, 그래프
6. **서버/인프라** — FastAPI WebSocket, Pydantic 스키마, CI, uv/패키징
7. **Godot** — 2D 뷰어, 관찰자 UI, 상태 라벨, 실시간 그래프

## 14. 가장 큰 기술적 위험 (우선순위)
1. **PPO가 규칙 기반을 못 이김** → 매크로 행동, 작은 관찰, 1M step 이내 학습 가능한 난이도로 시작. 못 이겨도 "왜 못 이겼는지" 분석이 결과물.
2. **순수 Python 시뮬레이션 속도** → 목표 단일 env ≥ 3,000 steps/s. 개체 9마리 규모라 numpy 과설계 금지, 프로파일 후 최적화.
3. **보상 hacking** → potential-based shaping, component 로깅, detector를 Phase 3에서 자동화.
4. **결정성 붕괴** (dict 순서, 전역 random, float 누적) → 스냅샷 해시 테스트를 Phase 1부터 CI에.
5. **Godot 학습 곡선** → Phase 4로 미루고 2D·도형 렌더링만.

---

## 환경 메모 (이 PC)
- `uv` 설치됨 → `uv python install 3.12`로 Python 3.12 사용. 시스템 python은 Store 스텁이라 사용 안 함.
- Godot 미설치 → Phase 4 전에 Godot 4.x stable(.NET 아님, GDScript) 설치 필요.
