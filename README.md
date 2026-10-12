# PaleoSphere AI

초식공룡과 육식공룡이 먹이·물·에너지를 두고 상호작용하는 생태계 시뮬레이터.
같은 환경·같은 관찰·같은 행동 공간에서 **규칙 기반 포식자(기준선)** 와 **PPO로 학습한 포식자** 를 수치로 비교한다.

> 행동 트리·상태 머신을 AI라고 부르지 않는다. 규칙 기반 정책은 기준선이고,
> AI 작업은 관찰·행동·보상 설계, PPO 학습, reward hacking 분석, 일반화 평가다.

- **웹 데모 (설치 없이 브라우저에서 실행)**: https://jngbnss.github.io/paleosphere-ai/ — 규칙 vs PPO 포식자 라이브 비교, Exp 001–004 결과
  (`pages/`, 시뮬레이터 JS 이식 `pages/sim.js`, 검증 `scripts/web-demo/`)
- 진행 상황·설계: [PLAN.md](PLAN.md) · 앞으로 할 일: [TODO.md](TODO.md)
- 스펙: [docs/office-hours.md](docs/office-hours.md) · [docs/environment-spec.md](docs/environment-spec.md)
- 실험 기록: [docs/experiments.md](docs/experiments.md) · 보상 설계: [docs/reward-design.md](docs/reward-design.md)
- 모델 선택: [docs/model-selection.md](docs/model-selection.md) · 프로토콜: [docs/protocol.md](docs/protocol.md)
- 결정 기록: [docs/decision-log.md](docs/decision-log.md) · 라이선스: [docs/licenses.md](docs/licenses.md)

## 구조

```
simulator/paleosphere/   결정론적 생태계 시뮬레이션 (그래픽 없음), 정책(Random·Rule·PPO), 관찰 생성
training/                Gymnasium 환경 PaleoSpherePredator-v0, 보상, PPO·BC 학습, 평가, hacking 탐지
inference-server/app/    FastAPI: WebSocket 스냅샷 스트리밍, /predict, 브라우저 뷰어
godot/                   Godot 4 뷰어: 3D 1인칭 탐험 + 2D 관찰자 (렌더링·제어만, 시뮬레이션은 서버)
configs/                 월드·정책·보상·학습 설정 (YAML)
evals/                   고정 평가 seed, reward hacking 탐지 기준
analytics/reports/       평가 CSV·요약·그래프
```

## 설치

[uv](https://docs.astral.sh/uv/) 필요.

```sh
uv python install 3.12
uv sync --all-extras
```

## 데모 실행 (관찰자 모드)

1. 학습 모델 준비 (한 번만, 약 5분). 모델 파일은 Git에 없다.
   ```sh
   uv run python -m training.scripts.train_ppo --config ppo_v2 --seed 1
   mkdir models
   cp training/checkpoints/ppo_v2_s1/final_model.zip models/ppo-v2.zip
   cp training/checkpoints/ppo_v2_s1/metadata.json models/ppo-v2.metadata.json
   ```
   (`models/`에 넣은 `*.zip`은 파일 이름으로 정책 목록에 나타나고, `ppo`는 가장 높은 `ppo-v<N>`을 가리킨다.)
2. 서버 + Godot 뷰어 한 번에 실행 (Windows):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Godot <Godot 실행 파일 경로>
   ```
   기본은 **3D 1인칭 탐험**(아래)이다. 2D 관찰 뷰어는 `-View2D`. 창 없이 연결만 검사: `scripts\dev.ps1 -Smoke`
   또는 따로:
   ```sh
   uv run python -m app                                   # http://127.0.0.1:8790
   godot --path godot res://scenes/explore3d.tscn         # 3D 탐험
   godot --path godot                                     # 2D 관찰 뷰어
   ```
   Godot이 없으면 브라우저에서 http://127.0.0.1:8790/ 를 열면 같은 데이터를 보는 간단한 뷰어가 뜬다.
3. 뷰어에서 seed·맵·포식자 정책(rule / random / ppo)을 고르고 **시작**. 공룡을 클릭하면 상태가 보인다.
   리플레이: `uv run python -m paleosphere.run --seed 42 --replay replays/seed42.jsonl` 후 뷰어의 **리플레이 열기**.

### 3D 1인칭 탐험

연구원이 되어 번식 생태계(`ecosystem` 맵, 포식자 ppo · 초식 herd-v1)를 직접 걸어 다닌다.
공룡은 기본 도형으로 조립한 저폴리 모델(초식=사우로포드, 육식=수각류)이고, 서버 시뮬레이션을 그대로 따라 움직인다.

| 키 | 동작 |
|---|---|
| 마우스 / WASD / Shift | 둘러보기 · 걷기 · 달리기 (처음에 화면 클릭) |
| 조준(+) | 가운데 공룡의 이름·상태·체력·배고픔·갈증 |
| E / R | 스캔 (근처 공룡 기록) · 현장 보고서 |
| F | 조준한 공룡 3인칭으로 따라가기 (F·WASD로 해제) |
| M · Space · [ ] · N | 미니맵 · 일시정지 · 속도 · 새 세계 |

시야 안에서 일어난 사냥·출생·죽음은 왼쪽에 알림으로 뜬다. 겹쳐 서는 무리는 화면에서만 살짝 벌려 보여 준다 (시뮬레이션 불변).
스모크: `godot --headless --path godot res://scenes/explore3d.tscn -- --smoke [--screenshot=a.png] [--follow]`

### ONNX 내보내기 + Godot 내부 추론

```sh
uv run python -m training.scripts.export_onnx --model models/ppo-v2.zip
# → models/ppo-v2.onnx (onnxruntime) + models/ppo-v2.policy.json (Godot·numpy)
```

- 내보낼 때 회귀 seed 에피소드 관찰 + 무작위 관찰(약 7,600개)에서 SB3·ONNX·numpy 행동이 모두 같은지 검사한다.
- 서버는 `models/*.onnx`를 `<이름>-onnx`로 등록한다. torch 없이 `uv sync --extra server --extra onnx`만으로도 서빙된다.
- Godot은 `models/ppo-v2.policy.json`이 있으면 정책 목록에 **godot-mlp**를 추가한다. 고르면 서버는 규칙만 돌리고
  포식자 행동은 Godot이 GDScript MLP로 직접 정한다 (`client` 모드, [protocol.md](docs/protocol.md)).
  다른 가중치: `godot --path godot -- --weights=<path>`.

### 탐험자 모드

오른쪽 패널 **탐험자 모드**를 켜고 **시작**하면 연구자(파란 마름모)가 맵 중앙에 선다.

| 키 | 동작 |
|---|---|
| WASD / 화살표 | 걷기 (시야 밖 공룡은 안 보이고, 안 가 본 곳은 어둡게) |
| E | 스캔 — 반경 안 공룡 식별, 현장 기록에 남김 |
| R | 현장 보고서 — 식별 개체, 추정 vs 실제 개체수, 관찰한 행동, 목격한 사냥·죽음·출생 |

탐험자는 시뮬레이션에 영향을 주지 않는다 (공룡이 보지 못함, 해시 동일).
보고서는 `user://field_report_<seed>_<tick>.md`에도 저장된다.

### 번식 생태계 · 학습 초식 무리

- 맵 `ecosystem`: 번식·노화가 켜진 장기 실행 (20,000 tick). 개체수 그래프, 개체의 세대·부모 표시 (Experiment 004)
- 초식 정책 `herd-v1`: 정책 공유 PPO로 학습한 초식 무리 (Experiment 005). 모델은 `models/herd-v1.zip`
  (`train_herd --config herd_v1 --seed 2` 후 `final_model.zip` 복사)

## 시뮬레이션·학습·평가 (그래픽 없음)

```sh
uv run python -m paleosphere.run --seed 42 --predator rule            # 에피소드 요약
uv run python -m paleosphere.run --seed 42 --predator onnx:models/ppo-v2.onnx   # torch 없이 PPO
uv run python -m training.scripts.train_ppo --config ppo_v2 --seed 0   # PPO (BC 사전학습 포함)
uv run python -m paleosphere.ecosystem --seeds 0-39 --ticks 20000       # 개체수 시계열 (Exp 004)
uv run python -m training.forecasting.population                     # 예측 모델 비교
uv run python -m training.scripts.train_herd --config herd_v1 --seed 0  # 초식 무리 (PettingZoo)
uv run python -m training.evaluation.evaluate \
    --policies rule random ppo=ppo:models/ppo-v2.zip \
    --sets eval_seen_map eval_unseen_map --out analytics/reports/my_eval
```

## 테스트

```sh
uv run ruff check .
uv run pytest
godot --headless --path godot --import                       # 프로젝트 로드 검사
godot --headless --path godot -- --smoke                     # 서버 연결 스모크 (서버 실행 중)
godot --headless --path godot -- --smoke-local --seed=10000  # Godot 내부 추론으로 에피소드 1회
uv run python -m training.scripts.export_onnx --fixture-out models/ppo-v2.fixture.json
godot --headless --path godot -- --mlp-check=../models/ppo-v2.fixture.json  # GDScript MLP 일치
godot --headless --path godot -- --smoke-explorer --report-out=r.md   # 탐험자 자동 걷기·스캔·보고서
```

## 결과 요약

[docs/experiments.md](docs/experiments.md) 참고. 각 20 seed 평균. 그래프: `analytics/reports/final/figures/`

| 정책 | 사냥 (처음 보는 seed) | 사냥 (처음 보는 맵 map_b) | 무효 공격 비율 | 포식자 사망률 |
|---|---|---|---|---|
| Random | 0.20 | 0.10 | 0.99 | 0.80 |
| Rule (기준선) | 2.10 | 2.25 | 0.56 | 0.00 |
| PPO v0 (보상 v0만) | 0.00 | 0.00 | – | 0.95–1.00 |
| PPO v1 (보상 v1 + BC + 커리큘럼) | 5.10–5.90 | 5.05–6.60 | 0.01–0.11 | 0.65–1.00 (탈수) |
| **PPO v2** (보상 v2, 배포 모델 `ppo-v2` = seed 1) | 5.45–7.05 | 4.75–7.15 | 0.02–0.12 | 0.05–0.25 |

## MVP 완료 조건

| # | 조건 | 상태 |
|---|---|---|
| 1 | 고정 seed로 생태계 초기화 | ✅ 스냅샷 해시 테스트 |
| 2 | 초식공룡이 규칙 기반으로 먹이·물을 찾음 | ✅ |
| 3 | 규칙 기반 육식공룡이 먹잇감 추격 | ✅ |
| 4 | 같은 환경에서 PPO 육식공룡 실행 | ✅ |
| 5 | 두 정책의 행동 차이가 화면에 표시 | ✅ Godot 상태 라벨·행동·지표 |
| 6 | 사냥 성공률·에너지 소비 비교 | ✅ `evaluate.py` |
| 7 | 새로운 seed에서 정책 평가 | ✅ eval_seen_map |
| 8 | 보지 않은 자원 배치에서 평가 | ✅ map_b, 자원 ±40% |
| 9 | Godot에서 학습 정책 실시간 작동 | ✅ |
| 10 | 개체 상태·행동 확인 | ✅ 클릭 선택 패널 |
| 11 | 고정 평가 스크립트로 재현 | ✅ `evals/fixed-seeds.yaml` |
| 12 | 실험 보고서에 개선 전후 기록 | ✅ Experiment 001–003 |
