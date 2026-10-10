# PaleoSphere AI

초식공룡과 육식공룡이 먹이·물·에너지를 두고 상호작용하는 생태계 시뮬레이터.
같은 환경에서 **규칙 기반 포식자(기준선)** 와 **PPO로 학습한 포식자** 를 수치로 비교한다.

- 설계·진행 상황: [PLAN.md](PLAN.md)
- 스펙: [docs/office-hours.md](docs/office-hours.md)
- 결정 기록: [docs/decision-log.md](docs/decision-log.md)

## 설치

[uv](https://docs.astral.sh/uv/) 필요.

```sh
uv python install 3.12
uv sync
```

## 테스트

```sh
uv run ruff check .
uv run pytest
```

## 시뮬레이션 실행 (그래픽 없음)

```sh
uv run python -m paleosphere.run --seed 42 --map map_a --predator rule --ticks 2000
uv run python -m paleosphere.run --seed 42 --predator random
uv run python -m paleosphere.run --seed 42 --replay replays/seed42.jsonl --replay-every 2
```
