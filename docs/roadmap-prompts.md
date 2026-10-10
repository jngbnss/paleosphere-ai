# PaleoSphere AI — 4단계 구현 프롬프트

각 Phase 프롬프트를 순서대로 Claude Code에 붙여 넣는다.
모든 Phase의 스펙 기준은 `docs/office-hours.md`다. 이전 Phase의 테스트가 통과한 상태에서 다음 Phase를 시작한다.

| Phase | 결과물 | 완료 판정 |
|---|---|---|
| 1 | 결정론적 Core Simulation + 규칙 기반 정책 + CLI + CI | 고정 seed 해시 테스트 통과, CLI로 에피소드 요약 출력 |
| 2 | Gymnasium 환경 + 보상 + PPO 학습 + 평가 스크립트 | `check_env` 통과, PPO vs Rule vs Random 비교표 생성 |
| 3 | Reward hacking 탐지 + 일반화 평가 + 실험 보고서 | `docs/experiments.md`에 개선 전후 결과 기록 |
| 4 | Sim 서버(WebSocket) + Godot 2D 관찰자 뷰어 | Godot에서 Rule/PPO 포식자 전환하며 실시간 관찰 |

---

## Phase 1 — Core Simulation + 규칙 기반 기준선

```
docs/office-hours.md를 스펙으로 읽고 Phase 1을 구현해줘.

목표: 그래픽 없이 돌아가는 결정론적 생태계 시뮬레이션과 규칙 기반 정책.

1. 프로젝트 세팅
   - uv로 Python 3.12 (`uv python install 3.12`), 루트 pyproject.toml 하나, 패키지는 simulator/paleosphere
   - 의존성: numpy, pyyaml, pydantic. 개발: pytest, ruff
   - .gitignore (checkpoints/, runs/, *.zip, .venv, __pycache__, replays/)
   - README.md 기본 구성 (설치·실행·테스트 방법)
2. Core Simulation (simulator/paleosphere/)
   - core/: World, tick 루프 (office-hours §3의 고정 순서), SeedSequence 기반 rng 분리, to_snapshot(), snapshot_hash()
   - entities/: Dino dataclass, Species 파라미터
   - resources/: PlantPatch, WaterSource, Rock, 맵 생성 (map_a, map_b)
   - combat/: 공격 사거리·쿨다운·명중·피해·사냥 성공 시 섭취
   - 대사 규칙: 에너지/배고픔/갈증/사망 원인
   - 낮/밤 사이클 (밤 시야 ×0.6)
   - configs/world/default.yaml, configs/world/map_b.yaml, configs/policies/rule_based.yaml
3. Policy Layer (simulator/paleosphere/policies/)
   - Policy 프로토콜: reset(seed), predict(observation_or_ctx) -> Action, get_metadata()
   - PredatorAction enum (7개), HerbivoreAction enum
   - RandomPolicy, RuleBasedPredator, RuleBasedHerbivore (office-hours §4 그대로, 수치는 yaml)
   - 포식자 관찰 벡터 생성 함수 build_predator_observation(world, agent_id) — §5의 26차원, Phase 2 Gym env에서 재사용
4. logging/: 에피소드 요약(생존 tick, kills, 공격 시도, 사망 원인, 행동 분포)과 jsonl 리플레이(tick별 스냅샷) 저장
5. CLI: `uv run python -m paleosphere.run --seed 42 --map map_a --predator rule --ticks 2000 [--replay out.jsonl]`
   → 에피소드 요약 출력
6. 테스트 (simulator/tests/)
   - 같은 seed 2회 실행 → snapshot_hash 동일 / 다른 seed → 다름
   - 관찰 벡터 shape=26, 값 범위 [-1,1], NaN 없음
   - 대사 규칙 단위 테스트 (굶주림 사망, 갈증 사망, 휴식 회복)
   - 전투 단위 테스트 (사거리 밖 공격 실패, 쿨다운)
   - 규칙 기반 회귀: seed 42/777/2026 결과 요약을 tests/golden/에 저장해 비교
   - 성능: 단일 에피소드 steps/s 측정 출력 (목표 ≥ 3000, 실패해도 테스트는 경고만)
7. CI: .github/workflows/ci.yml (permissions: contents: read, uv 설치, ruff check, pytest)
8. docs/decision-log.md에 Phase 1 결정사항 추가, docs/environment-spec.md 초안 작성

작은 단위로 구현하고 각 단위마다 테스트를 돌려. 마지막에 ruff + pytest 전체 통과 결과와
rule/random 포식자로 seed 42 실행한 요약을 보여줘. 커밋은 하지 말고 끝나면 알려줘.
```

---

## Phase 2 — Gymnasium 환경 + PPO 학습 + 기준선 비교

```
docs/office-hours.md와 Phase 1 코드를 기준으로 Phase 2를 구현해줘.

목표: 포식자 1마리를 PPO로 학습하고 Random / RuleBased와 같은 seed에서 비교.

1. 의존성 추가 (training extra): gymnasium, stable-baselines3, torch(CPU), tensorboard, pandas, matplotlib
2. training/environments/predator_env.py
   - PaleoSpherePredator-v0 등록, 관찰 Box(-1,1,(26,)), 행동 Discrete(7)
   - 나머지 초식공룡은 RuleBasedHerbivore
   - terminated(포식자 사망 / 초식 전멸) vs truncated(max_steps) 구분
   - info: reward_components, kills, death_cause, action_counts
   - 맵·world config·reward config를 생성자 인자로 받음
3. training/rewards/: configs/rewards/v0.yaml 로드, component별 계산 (office-hours §7, distance는 potential-based)
4. training/scripts/train_ppo.py
   - SubprocVecEnv 8개, seed 인자, 하이퍼파라미터는 configs/training/ppo_v0.yaml
   - EvalCallback: eval_seen_map seed로 주기 평가 (학습 seed와 분리)
   - checkpoints/와 runs/(tensorboard)에 저장 (git 제외)
   - 실행 메타데이터(json): 하이퍼파라미터, seed, env 버전, reward config, git hash, 모델 sha256
   - `--smoke` 옵션: 2,048 step만 돌고 종료 (CI용)
5. simulator/paleosphere/policies/ppo_policy.py: PPOPolicy가 체크포인트를 로드해 Policy 프로토콜 구현
6. training/evaluation/evaluate.py
   - evals/fixed-seeds.yaml 생성 (office-hours §10)
   - 정책(random/rule/ppo:<path>) × seed 세트 → 에피소드별 지표 CSV + 요약표(평균±표준편차)
   - office-hours §11 지표 전부
7. 테스트: gymnasium check_env, 관찰 space 포함 검사, 보상 NaN/inf 검사, 결정성(같은 seed+같은 행동열 → 같은 보상열),
   랜덤 정책 짧은 에피소드, train_ppo --smoke
8. 실제 학습: 학습 seed 0,1,2로 각각 500k step (시간이 너무 오래 걸리면 steps/s 측정 후 가능한 만큼 줄이고 그 사실을 기록)
9. 평가 실행 후 결과를 docs/experiments.md에 "Experiment 001: PPO v0 vs Rule vs Random" 형식
   (가설→환경 버전→정책 버전→보상 설정→학습 seed→평가 seed→기준선→결과→실패 원인→다음 실험)으로 기록
10. CI에 check_env + smoke training 추가

보상 총점만으로 좋아졌다고 판단하지 마. 행동 분포도 같이 보고해.
```

---

## Phase 3 — Reward Hacking 탐지 + 일반화 평가 + 보고서

```
Phase 2 결과를 바탕으로 Phase 3을 진행해줘.

목표: 학습된 정책의 이상 행동을 자동 탐지하고, 보상을 고쳐 재학습하고, 보지 않은 맵에서 평가.

1. training/evaluation/hacking_detectors.py
   - office-hours §7 표의 6개 detector (idle_forever, shadowing, attack_spam, water_farming,
     boundary_hugging, chase_to_death), 임계값은 evals/reward-hacking-cases.yaml
   - evaluate.py 결과에 detector 플래그 컬럼 추가
2. 각 detector를 고의로 유발하는 고정 seed + 스크립트 정책 테스트 (detector가 실제로 잡는지 검증)
3. Experiment 001의 PPO 정책에 detector 적용 → 발견된 문제를 docs/reward-design.md에 정리
4. configs/rewards/v1.yaml로 보상 수정 (근거를 reward-design.md에 기록), 학습 seed 0,1,2로 재학습
5. 일반화 평가: eval_seen_map, eval_unseen_map(map_b), 자원량 ±40% 변형에서 Random/Rule/PPO v0/PPO v1 비교
6. analytics/reports/: matplotlib 그래프 생성 스크립트
   - 정책별 생존 tick·사냥 성공률·사냥당 에너지 박스플롯
   - 행동 분포 막대그래프, 사망 원인 분포
   - 학습 곡선 (tensorboard 로그에서 추출)
7. docs/experiments.md에 Experiment 002 (reward v1) 기록, 개선 전후 비교표 포함
8. docs/model-selection.md: 어떤 체크포인트를 "ppo-v1"로 채택했는지 다중 지표 근거
9. 채택 모델을 Phase 4 서빙용으로 models/ppo-v1.zip 경로 규약 정의 (git 제외, README에 재현 명령 기록)

PPO가 Rule을 못 이기면 숨기지 말고 원인 분석을 보고서에 써.
```

---

## Phase 4 — Sim 서버 + Godot 2D 관찰자 뷰어

```
Phase 3까지의 코드로 Phase 4를 구현해줘. Godot 4.x는 설치되어 있다고 가정 (경로를 먼저 확인해줘).

목표: Python이 시뮬레이션을 돌리고 Godot이 실시간으로 관찰하는 MVP 데모.

1. inference-server/app/ (FastAPI)
   - Pydantic 스키마: Snapshot, DinoState, ControlCommand(start/pause/resume/set_speed/select), PredictRequest/Response
   - WebSocket /ws/sim: start(seed, map, predator_policy=rule|ppo|random) 받으면 World를 돌리며 tick 스냅샷 push (기본 10 tick/s, set_speed로 0.5x~20x)
   - 스냅샷에 각 포식자의 관찰 기반 상태 라벨 포함 (탐색 중/먹잇감 발견/추격 중/공격 준비/에너지 부족/물 탐색/추격 포기/휴식)
     — "모델의 생각"이 아니라 관찰값+선택 행동의 사람용 변환임을 코드 주석과 docs에 명시
   - 누적 지표(살아있는 초식 수, 포식자 에너지, kills, 공격 시도)를 스냅샷에 포함
   - POST /predict: {agent_id, observation} → {action, policy_version, inference_time_ms}
   - GET /health, GET /policies
   - 테스트: pytest + TestClient로 WebSocket 시작→스냅샷 수신→pause, /predict 응답 스키마, 추론 지연 측정
   - docs/protocol.md에 JSON Schema 내보내기
2. godot/ (Godot 4, GDScript, 2D)
   - WebSocketPeer 클라이언트, 스냅샷 보간 렌더링 (simulation tick과 FPS 분리)
   - 도형 기반: 초식(초록 원), 포식자(빨간 삼각형, 진행 방향), 식물(크기=먹이량), 물, 바위, 밤이면 어둡게
   - 관찰자 UI: 시작 패널(seed, 맵, 포식자 정책 선택), 일시정지/속도, 클릭으로 공룡 선택 → 상태 패널(에너지/배고픔/갈증/체력/행동/라벨)
   - 선택 공룡 머리 위 상태 라벨, 포식자 시야 원 토글
   - 하단 실시간 그래프: 초식 개체수, 포식자 에너지
   - 리플레이 모드: Phase 1의 jsonl 리플레이 파일 재생 (서버 없이)
   - headless 검사: `godot --headless --path godot --quit` 로 프로젝트 로드 에러 없는지 확인
3. 루트 스크립트: scripts/dev.ps1 (서버 실행) + README에 데모 실행 순서
4. CI에 서버 테스트 추가 (Godot headless 검사는 Godot 설치 단계 포함해 별도 job, 실패해도 전체 막지 않게 continue-on-error)
5. docs/licenses.md: 사용 라이브러리 버전·라이선스 표
6. office-hours 완료 조건 중 MVP 범위(1~7, 9~11)를 체크리스트로 README에 정리하고 각 항목 상태 표시

마지막에 서버를 띄우고 rule 정책과 ppo 정책으로 각각 seed 10000 스냅샷 몇 개를 받아 차이를 요약해줘.
```

---

## MVP 이후 (Phase 5+ 후보)
- 탐험자 모드 (플레이어 이동, 스캔, 생태 보고서)
- 번식 + 개체수 시계열 예측 (기준선 → 선형 → GBM, MAE/RMSE)
- ONNX 내보내기 + Godot 내부 추론
- PettingZoo 다중 에이전트 (초식공룡 학습, 정책 공유)
