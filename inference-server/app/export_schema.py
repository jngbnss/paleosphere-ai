"""Write docs/protocol.md with JSON Schemas of every wire message.

    uv run python -m app.export_schema
"""

from __future__ import annotations

import json

from app import schemas
from paleosphere.config import REPO_ROOT

INTRO = """# Sim Server Protocol

Python 시뮬레이션 서버(`inference-server/app`)와 Godot 뷰어 사이의 메시지 형식.
이 문서는 `uv run python -m app.export_schema`로 생성된다. 직접 수정하지 않는다.

## 흐름

1. Godot → `ws://127.0.0.1:8790/ws/sim` 연결
2. 서버 → `hello` (사용 가능한 정책·맵)
3. Godot → `start` (seed, map, predator_policy, ticks_per_second)
4. 서버 → 매 tick `snapshot` (실행 중일 때). `pause` / `resume` / `set_speed` / `step`으로 제어
5. 오류 시 서버 → `error`

### 탐험자 모드

`start.explorer = true`이면 맵 중앙에 탐험자(현장 연구자)가 생긴다. 탐험자는 시뮬레이션에 영향을
주지 않는다 (공룡이 보지 못하고 world 상태를 바꾸지 않음 → 해시 동일).

- `explorer_move` (x, z): 이동. 스냅샷의 `explorer`에 위치·탐사 격자가 실린다
- `scan`: 반경 안 공룡을 식별 → `scan_result`. 현장 기록에 쌓인다
- `report`: 현장 기록 → `report` (마크다운 보고서 + 통계, 추정 개체수 vs 실제)
- 시야 반경 안에서 일어난 사냥·죽음·출생은 매 tick 자동으로 목격 기록에 남는다

### client 모드 (Godot 내부 추론)

`start.predator_policy = "client"`이면 포식자 행동을 뷰어가 정한다.

1. 서버 → `snapshot` (tick t, `predator_observation` 26차원 포함)
2. Godot → `action` (`tick: t`, `action`: 0–6). Godot은 `*.policy.json` 가중치로 직접 추론
3. 서버가 그 행동으로 1 tick 진행 → tick t+1 `snapshot`. 행동이 올 때까지 기다린다
4. `tick`이 현재 tick과 다르면 `error`, 무시한다. client 모드에서 `step`은 쓰지 않는다

시뮬레이션은 서버에서만 실행된다. Godot은 렌더링과 제어 명령만 담당한다 (D-002).
client 모드에서도 Godot은 포식자 행동만 정하고 규칙·상태 갱신은 서버가 한다.
`status_label`은 관찰값과 선택된 행동을 사람이 읽기 쉽게 바꾼 것이며 모델 내부 추론을 뜻하지 않는다.

HTTP: `GET /health`, `GET /policies`, `POST /predict` (관찰 26차원 → 행동).
"""

SECTIONS = [
    ("Server → Client: Snapshot", schemas.Snapshot),
    ("Server → Client: Hello", schemas.Hello),
    ("Server → Client: Error", schemas.ErrorMessage),
    ("Server → Client: ScanResult (탐험자)", schemas.ScanResult),
    ("Server → Client: FieldReport (탐험자)", schemas.FieldReport),
    ("Client → Server: ControlCommand", schemas.control_adapter),
    ("POST /predict 요청", schemas.PredictRequest),
    ("POST /predict 응답", schemas.PredictResponse),
]


def render() -> str:
    parts = [INTRO]
    for title, model in SECTIONS:
        schema = model.json_schema() if hasattr(model, "json_schema") else model.model_json_schema()
        body = json.dumps(schema, indent=2, ensure_ascii=False)
        parts.append(f"## {title}\n\n```json\n{body}\n```\n")
    return "\n".join(parts)


def main() -> None:
    path = REPO_ROOT / "docs" / "protocol.md"
    path.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
