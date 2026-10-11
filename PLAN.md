# PaleoSphere AI — 설계 및 구현 계획

스펙 상세: [`docs/office-hours.md`](docs/office-hours.md) · 붙여넣기용 프롬프트: [`docs/roadmap-prompts.md`](docs/roadmap-prompts.md) · 결정 기록: [`docs/decision-log.md`](docs/decision-log.md)

---

## 작업 규칙

1. 작업 시작 전 이 문서의 해당 항목 상태를 **🔄 진행중**으로 바꾸고 커밋·푸시한다.
2. 구현한다.
3. 항목에 적힌 **스모크 테스트**를 실행한다. (Phase 1 이후는 `ruff check` + `pytest`도 함께)
4. 문제가 없으면 **✅ 완료**로 바꾸고 결과 한 줄을 기록한 뒤 커밋·푸시한다.
5. 실패하면 상태를 **⚠️ 막힘**으로 바꾸고 원인을 비고에 적는다.

상태 표기: ⬜ 대기 · 🔄 진행중 · ✅ 완료 · ⚠️ 막힘

---

## 1. 설계 개요

### 1.1 계층 구조

```
┌──────────────────────┐   WebSocket (스냅샷 push / 제어 명령)
│  Godot 2D Viewer     │◄──────────────────────────────┐
│  렌더링·UI만 담당     │                               │
└──────────────────────┘                               │
                                          ┌────────────┴───────────┐
                                          │ Sim Server (FastAPI)   │
                                          │ World 실행 + /predict  │
                                          └────────────┬───────────┘
┌──────────────────────┐                               │
│ Training (SB3 PPO)   │── Gymnasium Env ──┐           │
│ Evaluation / Reports │                   ▼           ▼
└──────────────────────┘          ┌──────────────────────────┐
                                  │ Core Simulation (Python) │
                                  │ 결정론적 tick, 규칙       │
                                  ├──────────────────────────┤
                                  │ Policy Layer             │
                                  │ Random/Rule/PPO          │
                                  └──────────────────────────┘
```

- **Core Simulation이 유일한 진실.** 학습·평가·서버·Godot 모두 같은 코드를 사용한다.
- **AI 영역**: Gym 환경(관찰/행동/보상 설계), PPO 학습, hacking 탐지, 일반화 평가.
- **AI 아님**: 시뮬레이션 규칙, 규칙 기반 정책(기준선), 렌더링.

### 1.2 디렉토리 구조

```
paleosphere-ai/
├─ pyproject.toml              # uv, Python 3.12, 단일 프로젝트
├─ configs/
│  ├─ world/                   # default.yaml(map_a), map_b.yaml
│  ├─ policies/                # rule_based.yaml
│  ├─ rewards/                 # v0.yaml, v1.yaml
│  └─ training/                # ppo_v0.yaml
├─ simulator/
│  ├─ paleosphere/
│  │  ├─ core/                 # World, tick 루프, rng, snapshot/hash
│  │  ├─ entities/             # Dino, Species
│  │  ├─ resources/            # Plant, Water, Rock, 맵 생성
│  │  ├─ combat/               # 공격·명중·피해
│  │  ├─ policies/             # Policy 프로토콜, Random, RuleBased, PPO, 관찰 생성
│  │  ├─ logging/              # 에피소드 요약, jsonl 리플레이
│  │  └─ run.py                # CLI
│  └─ tests/
├─ training/
│  ├─ environments/            # PaleoSpherePredator-v0
│  ├─ rewards/                 # component별 보상 계산
│  ├─ scripts/                 # train_ppo.py
│  ├─ evaluation/              # evaluate.py, hacking_detectors.py
│  └─ checkpoints/             # (git 제외)
├─ inference-server/app/       # FastAPI, WebSocket, Pydantic 스키마
├─ godot/                      # Godot 4 2D 뷰어
├─ analytics/reports/          # 그래프 생성 스크립트
├─ evals/                      # fixed-seeds.yaml, reward-hacking-cases.yaml
├─ docs/
└─ .github/workflows/ci.yml
```

### 1.3 핵심 설계 결정
| 항목 | 결정 |
|---|---|
| 좌표 | 2D 연속 `(x, z)`, 맵 64×64 |
| 시간 | 고정 tick, FPS와 분리 |
| 결정성 | `SeedSequence.spawn`으로 하위 시스템별 rng, `agent_id` 정렬 순회, 스냅샷 해시 테스트 |
| 기본 시나리오 | 포식자 1, 초식 8, 식물 10, 물 2, 바위 6, 낮/밤 |
| 포식자 관찰 | `Box(-1,1,(26,))` — 자기 상태, 먹잇감, 물, 장애물, 추격 시간, 쿨다운, 밤, 직전 행동 |
| 포식자 행동 | `Discrete(7)` — SEARCH, APPROACH, CHASE, ATTACK, GO_TO_WATER, REST, GIVE_UP |
| 보상 | component별 기록, 거리 보상은 potential-based, 생존 보상 v0에서 0 |
| 평가 seed | train 0–9999 / eval 10000–10019(map_a) / unseen 20000–20019(map_b) / 회귀 42·777·2026 |
| 연동 | Python이 sim 실행, Godot은 WebSocket으로 스냅샷 수신 |

---

## 2. 단계별 구현 계획

### Phase 0 — 기획·설계

| # | 작업 | 상태 | 스모크 테스트 | 비고 |
|---|---|---|---|---|
| 0.1 | 오피스 아워, 스펙·결정 로그·프롬프트 작성 | ✅ 완료 | 문서 존재 확인 | `docs/` |
| 0.2 | 설계·구현 계획 문서 (이 문서) | ✅ 완료 | 문서 존재 확인 | `PLAN.md` |

### Phase 1 — Core Simulation + 규칙 기반 기준선

| # | 작업 | 상태 | 스모크 테스트 | 비고 |
|---|---|---|---|---|
| 1.1 | uv 프로젝트 세팅 (pyproject, .gitignore, README) | ✅ 완료 | `uv run python -c "import paleosphere"` | import ok, Python 3.12 |
| 1.2 | 엔티티·자원·맵 생성 + world config yaml | ✅ 완료 | seed로 맵 생성 후 개체 수 확인 | map_a/map_b 생성 테스트 6개 통과 |
| 1.3 | World tick 루프 + 대사·사망 규칙 + 낮/밤 | ✅ 완료 | 정책 없이(전원 REST) 2500 tick, 굶주림·갈증 사망 발생 | world 테스트 9개 포함 15개 통과 |
| 1.4 | 전투 (사거리·쿨다운·명중·사냥) | ✅ 완료 | 전투 단위 테스트 | 전투 테스트 8개 포함 23개 통과 |
| 1.5 | Policy 프로토콜 + Random + RuleBased(초식·육식) + 관찰 생성(26차원) | ✅ 완료 | 관찰 shape/범위/NaN 테스트 | 31개 통과. 8 seed 기준 Rule 포식자 사냥 2~3회 생존, Random 사냥 0회 굶어 죽음 |
| 1.6 | 결정성 (snapshot hash) + 골든 회귀 테스트 | ✅ 완료 | seed 42 두 번 실행 해시 동일 | 38개 통과. seed 42/777/2026 골든 요약+해시 일치 |
| 1.7 | 에피소드 로그 + jsonl 리플레이 + CLI | ✅ 완료 | `python -m paleosphere.run --seed 42` 요약 출력 | CLI seed 42: 사냥 2, 2,960 steps/s. 리플레이 왕복 테스트 통과 (42개) |
| 1.8 | CI (ruff + pytest) + environment-spec.md | ✅ 완료 | 로컬 ruff + pytest 통과 | 로컬 ruff+pytest 42개 통과. CI ubuntu/windows 매트릭스 |

### Phase 2 — Gymnasium 환경 + PPO 학습

| # | 작업 | 상태 | 스모크 테스트 | 비고 |
|---|---|---|---|---|
| 2.1 | 학습 의존성 추가 | ✅ 완료 | `import gymnasium, stable_baselines3` | gymnasium 1.4.0, SB3 2.9.0, torch 2.14.1+cpu import·연산 확인 |
| 2.2 | 보상 v0 (component별) | ✅ 완료 | 보상 NaN/inf 테스트 | component 10종 + total. NaN/inf·사냥·무효공격·사망·shaping 루프 테스트 통과 (48개) |
| 2.3 | `PaleoSpherePredator-v0` 환경 | ✅ 완료 | `check_env` 통과 | check_env 통과, terminated/truncated 구분, 순수 sim과 해시 일치 |
| 2.4 | `train_ppo.py` (+ `--smoke`, 메타데이터, EvalCallback) | ✅ 완료 | `--smoke` 2,048 step 완료 | --smoke 11초 통과. 50k step 27초 (8 env 약 2,000 steps/s) |
| 2.5 | `PPOPolicy` + `evaluate.py` + `fixed-seeds.yaml` | ✅ 완료 | random/rule 정책 3 seed 평가 CSV 생성 | 3 seed: Rule 사냥 1.67·생존 2000, Random 사냥 0·전원 사망. PPOPolicy 어댑터 테스트 통과 |
| 2.6 | 학습 seed 0·1·2 학습 + 비교 → Experiment 001 | ✅ 완료 | 비교표 생성 | Exp 001: PPO v0 3 seed 모두 사냥 0 (GIVE_UP 정지로 수렴), Rule 2.10 → 가설 기각, 원인 분석 기록 |
| 2.7 | CI에 check_env + smoke training | ✅ 완료 | 로컬 pytest 통과 | 로컬 pytest 59개 통과, check_env·smoke 단계 CI 추가 |

### Phase 3 — Reward Hacking + 일반화 평가

| # | 작업 | 상태 | 스모크 테스트 | 비고 |
|---|---|---|---|---|
| 3.1 | hacking detector 6종 + 유발 테스트 | ✅ 완료 | 각 detector가 유발 케이스 탐지 | 탐지기 6종. REST·ATTACK·물·추격 스크립트 정책에서 각각 탐지, Rule 기준선은 탐지 없음 (67개 통과) |
| 3.2 | PPO v0 분석 → reward-design.md | ✅ 완료 | 문서 확인 | 원인 3가지(shaping 근접 세금·탐색 실패·탐지기 사각지대)와 v1 수정 근거 기록 |
| 3.3 | 보상 v1 + 재학습 | ✅ 완료 | `--smoke` + 학습 완료 | v1(BC+커리큘럼) seed 0·1·2 각 500k, 학습 중 평가 사냥 5.6~6.6 (v0 0). v1 smoke 테스트 추가 |
| 3.4 | 일반화 평가 (unseen seed / map_b / 자원 ±40%) | ✅ 완료 | 평가 CSV 생성 | PPO v1 사냥 5.1~6.6 (Rule 2.1~2.3), 처음 보는 seed·map_b·자원 ±40%에서 유지. 단 탈수 사망 65~100% → dehydration_neglect 탐지기 추가 |
| 3.5 | 그래프 + Experiment 002 + model-selection.md | ✅ 완료 | 그래프 파일 생성 | 그래프 5종(박스플롯·행동 분포·결말·학습 곡선), Exp 002·003 기록, model-selection.md → ppo_v2_s1을 models/ppo-v2.zip으로 배포 |
| 3.6 | 보상 v2 (갈증 비례 비용) 재학습 → Experiment 003 | ✅ 완료 | 평가 CSV + 탐지기 | v2 탈수 사망률 0.65~1.00 → 0.05~0.25, 사냥 4.75~7.15 유지 (Rule 2.1~2.25). Exp 003 기록 |

### Phase 4 — Sim 서버 + Godot 관찰자 뷰어

| # | 작업 | 상태 | 스모크 테스트 | 비고 |
|---|---|---|---|---|
| 4.1 | Pydantic 스키마 + protocol.md | ✅ 완료 | 스키마 검증 테스트 | Snapshot·Command·Predict 스키마, 상태 라벨, protocol.md 자동 생성·동기화 테스트 통과 |
| 4.2 | FastAPI `/ws/sim`, `/predict`, `/health`, `/policies` | ✅ 완료 | TestClient로 스냅샷 수신 | /health·/policies·/predict·/ws/sim(start·pause·step·error) TestClient 11개 통과. 브라우저 대체 뷰어 GET / |
| 4.3 | Godot 프로젝트 + WebSocket 클라이언트 + 렌더링 | ✅ 완료 | `godot --headless --quit` 에러 없음 | Godot 4.7.2 import 에러 없음, headless --smoke: 서버 snapshot 20개 수신 (SMOKE OK) |
| 4.4 | 관찰자 UI (정책 선택, 속도, 선택 패널, 라벨, 그래프) | ✅ 완료 | 서버 연결 후 화면 확인 | 정책·맵·seed 선택, 일시정지/속도, 클릭 선택 패널(게이지), 상태 라벨, 시야, 실시간 그래프. 창 모드 스크린샷 확인 |
| 4.5 | 리플레이 모드 + dev 스크립트 + licenses.md + README 체크리스트 | ✅ 완료 | 리플레이 파일 재생 | Godot 리플레이 재생 headless 스모크 통과, scripts/dev.ps1, licenses.md, README 데모·MVP 체크리스트 |

### Phase 5 — ONNX 내보내기 + Godot 내부 추론

| # | 작업 | 상태 | 스모크 테스트 | 비고 |
|---|---|---|---|---|
| 5.1 | `export_onnx.py`: PPO actor → ONNX + Godot용 가중치 JSON | ✅ 완료 | 고정 관찰 세트에서 SB3·ONNX·JSON(numpy) 행동 일치 | ppo-v2 관찰 7,623개(회귀 seed 에피소드+무작위)에서 SB3·ONNX·numpy 행동 100% 일치, logit 차 3.8e-6. onnx.helper로 그래프 직접 구성. 84개 통과 |
| 5.2 | `OnnxPolicy` (onnxruntime, torch 불필요) + 서버 `models/*.onnx` 등록 | ✅ 완료 | 같은 seed에서 PPOPolicy와 에피소드 해시 일치, `/predict` 응답 | ppo-v2: map_a·map_b × seed 5개 = 10 에피소드 SB3·ONNX·MLP 해시 모두 일치. ONNX 약 5,400 steps/s (SB3 2,250). 서버 `ppo-v2-onnx` 등록·/predict 응답, torch 미설치 시 ONNX만 노출. 88개 통과 |
| 5.3 | Godot GDScript MLP + `client` 정책 모드 (서버는 관찰만 보내고 Godot이 행동 결정) | 🔄 진행중 | Godot headless: 고정 관찰 행동 일치 + client 모드 에피소드가 서버 ppo 실행과 해시 일치 | |

### MVP 이후
탐험자 모드 · 번식 + 개체수 시계열 예측 · PettingZoo 다중 에이전트
