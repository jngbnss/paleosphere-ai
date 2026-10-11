# Sim Server Protocol

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

## Server → Client: Snapshot

```json
{
  "$defs": {
    "DinoState": {
      "additionalProperties": false,
      "properties": {
        "agent_id": {
          "title": "Agent Id",
          "type": "string"
        },
        "species": {
          "enum": [
            "herbivore",
            "predator"
          ],
          "title": "Species",
          "type": "string"
        },
        "position": {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Position",
          "type": "array"
        },
        "velocity": {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Velocity",
          "type": "array"
        },
        "health": {
          "title": "Health",
          "type": "number"
        },
        "energy": {
          "title": "Energy",
          "type": "number"
        },
        "hunger": {
          "title": "Hunger",
          "type": "number"
        },
        "thirst": {
          "title": "Thirst",
          "type": "number"
        },
        "age": {
          "title": "Age",
          "type": "integer"
        },
        "current_action": {
          "title": "Current Action",
          "type": "string"
        },
        "target_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Target Id"
        },
        "alive": {
          "title": "Alive",
          "type": "boolean"
        },
        "death_cause": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Death Cause"
        },
        "status_code": {
          "title": "Status Code",
          "type": "string"
        },
        "status_label": {
          "title": "Status Label",
          "type": "string"
        },
        "vision": {
          "title": "Vision",
          "type": "number"
        },
        "generation": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Generation"
        },
        "parent_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Parent Id"
        },
        "breed_cooldown": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Breed Cooldown"
        }
      },
      "required": [
        "agent_id",
        "species",
        "position",
        "velocity",
        "health",
        "energy",
        "hunger",
        "thirst",
        "age",
        "current_action",
        "target_id",
        "alive",
        "death_cause",
        "status_code",
        "status_label",
        "vision"
      ],
      "title": "DinoState",
      "type": "object"
    },
    "EventState": {
      "additionalProperties": false,
      "properties": {
        "tick": {
          "title": "Tick",
          "type": "integer"
        },
        "kind": {
          "title": "Kind",
          "type": "string"
        },
        "agent_id": {
          "title": "Agent Id",
          "type": "string"
        },
        "target_id": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "title": "Target Id"
        },
        "data": {
          "additionalProperties": true,
          "title": "Data",
          "type": "object"
        }
      },
      "required": [
        "tick",
        "kind",
        "agent_id",
        "target_id",
        "data"
      ],
      "title": "EventState",
      "type": "object"
    },
    "ExplorerState": {
      "additionalProperties": false,
      "properties": {
        "position": {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Position",
          "type": "array"
        },
        "scan_radius": {
          "title": "Scan Radius",
          "type": "number"
        },
        "view_radius": {
          "title": "View Radius",
          "type": "number"
        },
        "scans": {
          "title": "Scans",
          "type": "integer"
        },
        "identified": {
          "title": "Identified",
          "type": "integer"
        },
        "explored_fraction": {
          "title": "Explored Fraction",
          "type": "number"
        },
        "explored": {
          "description": "GRID x GRID cells, [x][z]",
          "items": {
            "items": {
              "type": "boolean"
            },
            "type": "array"
          },
          "title": "Explored",
          "type": "array"
        }
      },
      "required": [
        "position",
        "scan_radius",
        "view_radius",
        "scans",
        "identified",
        "explored_fraction",
        "explored"
      ],
      "title": "ExplorerState",
      "type": "object"
    },
    "Metrics": {
      "additionalProperties": false,
      "properties": {
        "herbivores_alive": {
          "title": "Herbivores Alive",
          "type": "integer"
        },
        "predator_energy": {
          "title": "Predator Energy",
          "type": "number"
        },
        "predator_hunger": {
          "title": "Predator Hunger",
          "type": "number"
        },
        "kills": {
          "title": "Kills",
          "type": "integer"
        },
        "attack_attempts": {
          "title": "Attack Attempts",
          "type": "integer"
        },
        "invalid_attacks": {
          "title": "Invalid Attacks",
          "type": "integer"
        },
        "predators_alive": {
          "default": 1,
          "title": "Predators Alive",
          "type": "integer"
        },
        "births": {
          "default": 0,
          "title": "Births",
          "type": "integer"
        }
      },
      "required": [
        "herbivores_alive",
        "predator_energy",
        "predator_hunger",
        "kills",
        "attack_attempts",
        "invalid_attacks"
      ],
      "title": "Metrics",
      "type": "object"
    },
    "PlantState": {
      "additionalProperties": false,
      "properties": {
        "plant_id": {
          "title": "Plant Id",
          "type": "string"
        },
        "position": {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Position",
          "type": "array"
        },
        "radius": {
          "title": "Radius",
          "type": "number"
        },
        "food": {
          "title": "Food",
          "type": "number"
        }
      },
      "required": [
        "plant_id",
        "position",
        "radius",
        "food"
      ],
      "title": "PlantState",
      "type": "object"
    },
    "RockState": {
      "additionalProperties": false,
      "properties": {
        "rock_id": {
          "title": "Rock Id",
          "type": "string"
        },
        "position": {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Position",
          "type": "array"
        },
        "radius": {
          "title": "Radius",
          "type": "number"
        }
      },
      "required": [
        "rock_id",
        "position",
        "radius"
      ],
      "title": "RockState",
      "type": "object"
    },
    "WaterState": {
      "additionalProperties": false,
      "properties": {
        "water_id": {
          "title": "Water Id",
          "type": "string"
        },
        "position": {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Position",
          "type": "array"
        },
        "radius": {
          "title": "Radius",
          "type": "number"
        }
      },
      "required": [
        "water_id",
        "position",
        "radius"
      ],
      "title": "WaterState",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "type": {
      "const": "snapshot",
      "default": "snapshot",
      "title": "Type",
      "type": "string"
    },
    "protocol_version": {
      "default": 1,
      "title": "Protocol Version",
      "type": "integer"
    },
    "tick": {
      "title": "Tick",
      "type": "integer"
    },
    "seed": {
      "title": "Seed",
      "type": "integer"
    },
    "map": {
      "title": "Map",
      "type": "string"
    },
    "map_size": {
      "title": "Map Size",
      "type": "number"
    },
    "is_night": {
      "title": "Is Night",
      "type": "boolean"
    },
    "predator_policy": {
      "title": "Predator Policy",
      "type": "string"
    },
    "herbivore_policy": {
      "default": "rule",
      "title": "Herbivore Policy",
      "type": "string"
    },
    "paused": {
      "title": "Paused",
      "type": "boolean"
    },
    "ticks_per_second": {
      "title": "Ticks Per Second",
      "type": "number"
    },
    "done": {
      "title": "Done",
      "type": "boolean"
    },
    "dinos": {
      "items": {
        "$ref": "#/$defs/DinoState"
      },
      "title": "Dinos",
      "type": "array"
    },
    "plants": {
      "items": {
        "$ref": "#/$defs/PlantState"
      },
      "title": "Plants",
      "type": "array"
    },
    "waters": {
      "items": {
        "$ref": "#/$defs/WaterState"
      },
      "title": "Waters",
      "type": "array"
    },
    "rocks": {
      "items": {
        "$ref": "#/$defs/RockState"
      },
      "title": "Rocks",
      "type": "array"
    },
    "events": {
      "items": {
        "$ref": "#/$defs/EventState"
      },
      "title": "Events",
      "type": "array"
    },
    "metrics": {
      "$ref": "#/$defs/Metrics"
    },
    "explorer": {
      "anyOf": [
        {
          "$ref": "#/$defs/ExplorerState"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "explorer mode only"
    },
    "predator_observation": {
      "anyOf": [
        {
          "items": {
            "type": "number"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "client mode only: the 26-dim predator observation at this tick; reply with an `action` command for the same tick",
      "title": "Predator Observation"
    }
  },
  "required": [
    "tick",
    "seed",
    "map",
    "map_size",
    "is_night",
    "predator_policy",
    "paused",
    "ticks_per_second",
    "done",
    "dinos",
    "plants",
    "waters",
    "rocks",
    "events",
    "metrics"
  ],
  "title": "Snapshot",
  "type": "object"
}
```

## Server → Client: Hello

```json
{
  "additionalProperties": false,
  "properties": {
    "type": {
      "const": "hello",
      "default": "hello",
      "title": "Type",
      "type": "string"
    },
    "protocol_version": {
      "default": 1,
      "title": "Protocol Version",
      "type": "integer"
    },
    "policies": {
      "items": {
        "type": "string"
      },
      "title": "Policies",
      "type": "array"
    },
    "maps": {
      "items": {
        "type": "string"
      },
      "title": "Maps",
      "type": "array"
    },
    "herbivore_policies": {
      "default": [
        "rule"
      ],
      "items": {
        "type": "string"
      },
      "title": "Herbivore Policies",
      "type": "array"
    }
  },
  "required": [
    "policies",
    "maps"
  ],
  "title": "Hello",
  "type": "object"
}
```

## Server → Client: Error

```json
{
  "additionalProperties": false,
  "properties": {
    "type": {
      "const": "error",
      "default": "error",
      "title": "Type",
      "type": "string"
    },
    "message": {
      "title": "Message",
      "type": "string"
    }
  },
  "required": [
    "message"
  ],
  "title": "ErrorMessage",
  "type": "object"
}
```

## Server → Client: ScanResult (탐험자)

```json
{
  "$defs": {
    "Sighting": {
      "additionalProperties": false,
      "properties": {
        "agent_id": {
          "title": "Agent Id",
          "type": "string"
        },
        "species": {
          "enum": [
            "herbivore",
            "predator"
          ],
          "title": "Species",
          "type": "string"
        },
        "position": {
          "maxItems": 2,
          "minItems": 2,
          "prefixItems": [
            {
              "type": "number"
            },
            {
              "type": "number"
            }
          ],
          "title": "Position",
          "type": "array"
        },
        "distance": {
          "title": "Distance",
          "type": "number"
        },
        "alive": {
          "title": "Alive",
          "type": "boolean"
        },
        "status_label": {
          "title": "Status Label",
          "type": "string"
        },
        "current_action": {
          "title": "Current Action",
          "type": "string"
        },
        "health": {
          "title": "Health",
          "type": "number"
        },
        "energy": {
          "title": "Energy",
          "type": "number"
        },
        "hunger": {
          "title": "Hunger",
          "type": "number"
        },
        "thirst": {
          "title": "Thirst",
          "type": "number"
        },
        "new": {
          "description": "first time this individual is identified",
          "title": "New",
          "type": "boolean"
        }
      },
      "required": [
        "agent_id",
        "species",
        "position",
        "distance",
        "alive",
        "status_label",
        "current_action",
        "health",
        "energy",
        "hunger",
        "thirst",
        "new"
      ],
      "title": "Sighting",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "properties": {
    "type": {
      "const": "scan_result",
      "default": "scan_result",
      "title": "Type",
      "type": "string"
    },
    "tick": {
      "title": "Tick",
      "type": "integer"
    },
    "position": {
      "maxItems": 2,
      "minItems": 2,
      "prefixItems": [
        {
          "type": "number"
        },
        {
          "type": "number"
        }
      ],
      "title": "Position",
      "type": "array"
    },
    "radius": {
      "title": "Radius",
      "type": "number"
    },
    "sightings": {
      "items": {
        "$ref": "#/$defs/Sighting"
      },
      "title": "Sightings",
      "type": "array"
    }
  },
  "required": [
    "tick",
    "position",
    "radius",
    "sightings"
  ],
  "title": "ScanResult",
  "type": "object"
}
```

## Server → Client: FieldReport (탐험자)

```json
{
  "additionalProperties": false,
  "properties": {
    "type": {
      "const": "report",
      "default": "report",
      "title": "Type",
      "type": "string"
    },
    "tick": {
      "title": "Tick",
      "type": "integer"
    },
    "markdown": {
      "title": "Markdown",
      "type": "string"
    },
    "stats": {
      "additionalProperties": true,
      "title": "Stats",
      "type": "object"
    }
  },
  "required": [
    "tick",
    "markdown",
    "stats"
  ],
  "title": "FieldReport",
  "type": "object"
}
```

## Client → Server: ControlCommand

```json
{
  "$defs": {
    "ActionCommand": {
      "additionalProperties": false,
      "description": "Client mode: the predator action for `tick` (the tick of the snapshot it answers).",
      "properties": {
        "type": {
          "const": "action",
          "title": "Type",
          "type": "string"
        },
        "tick": {
          "minimum": 0,
          "title": "Tick",
          "type": "integer"
        },
        "action": {
          "description": "PredatorAction id",
          "maximum": 6,
          "minimum": 0,
          "title": "Action",
          "type": "integer"
        }
      },
      "required": [
        "type",
        "tick",
        "action"
      ],
      "title": "ActionCommand",
      "type": "object"
    },
    "ExplorerMoveCommand": {
      "additionalProperties": false,
      "description": "Explorer mode: walk to (x, z) (clamped to the map). Does not affect the simulation.",
      "properties": {
        "type": {
          "const": "explorer_move",
          "title": "Type",
          "type": "string"
        },
        "x": {
          "title": "X",
          "type": "number"
        },
        "z": {
          "title": "Z",
          "type": "number"
        }
      },
      "required": [
        "type",
        "x",
        "z"
      ],
      "title": "ExplorerMoveCommand",
      "type": "object"
    },
    "PauseCommand": {
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "pause",
          "title": "Type",
          "type": "string"
        }
      },
      "required": [
        "type"
      ],
      "title": "PauseCommand",
      "type": "object"
    },
    "ReportCommand": {
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "report",
          "title": "Type",
          "type": "string"
        }
      },
      "required": [
        "type"
      ],
      "title": "ReportCommand",
      "type": "object"
    },
    "ResumeCommand": {
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "resume",
          "title": "Type",
          "type": "string"
        }
      },
      "required": [
        "type"
      ],
      "title": "ResumeCommand",
      "type": "object"
    },
    "ScanCommand": {
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "scan",
          "title": "Type",
          "type": "string"
        }
      },
      "required": [
        "type"
      ],
      "title": "ScanCommand",
      "type": "object"
    },
    "SetSpeedCommand": {
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "set_speed",
          "title": "Type",
          "type": "string"
        },
        "ticks_per_second": {
          "exclusiveMinimum": 0,
          "maximum": 200,
          "title": "Ticks Per Second",
          "type": "number"
        }
      },
      "required": [
        "type",
        "ticks_per_second"
      ],
      "title": "SetSpeedCommand",
      "type": "object"
    },
    "StartCommand": {
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "start",
          "title": "Type",
          "type": "string"
        },
        "seed": {
          "default": 10000,
          "title": "Seed",
          "type": "integer"
        },
        "map": {
          "default": "map_a",
          "enum": [
            "map_a",
            "map_b",
            "ecosystem"
          ],
          "title": "Map",
          "type": "string"
        },
        "predator_policy": {
          "default": "rule",
          "title": "Predator Policy",
          "type": "string"
        },
        "herbivore_policy": {
          "default": "rule",
          "description": "rule | random | herd-<name> model",
          "title": "Herbivore Policy",
          "type": "string"
        },
        "explorer": {
          "default": false,
          "description": "explorer mode: a field researcher at map center",
          "title": "Explorer",
          "type": "boolean"
        },
        "ticks_per_second": {
          "default": 10.0,
          "exclusiveMinimum": 0,
          "maximum": 200,
          "title": "Ticks Per Second",
          "type": "number"
        }
      },
      "required": [
        "type"
      ],
      "title": "StartCommand",
      "type": "object"
    },
    "StepCommand": {
      "additionalProperties": false,
      "properties": {
        "type": {
          "const": "step",
          "title": "Type",
          "type": "string"
        },
        "n": {
          "default": 1,
          "maximum": 1000,
          "minimum": 1,
          "title": "N",
          "type": "integer"
        }
      },
      "required": [
        "type"
      ],
      "title": "StepCommand",
      "type": "object"
    }
  },
  "discriminator": {
    "mapping": {
      "action": "#/$defs/ActionCommand",
      "explorer_move": "#/$defs/ExplorerMoveCommand",
      "pause": "#/$defs/PauseCommand",
      "report": "#/$defs/ReportCommand",
      "resume": "#/$defs/ResumeCommand",
      "scan": "#/$defs/ScanCommand",
      "set_speed": "#/$defs/SetSpeedCommand",
      "start": "#/$defs/StartCommand",
      "step": "#/$defs/StepCommand"
    },
    "propertyName": "type"
  },
  "oneOf": [
    {
      "$ref": "#/$defs/StartCommand"
    },
    {
      "$ref": "#/$defs/PauseCommand"
    },
    {
      "$ref": "#/$defs/ResumeCommand"
    },
    {
      "$ref": "#/$defs/SetSpeedCommand"
    },
    {
      "$ref": "#/$defs/StepCommand"
    },
    {
      "$ref": "#/$defs/ActionCommand"
    },
    {
      "$ref": "#/$defs/ExplorerMoveCommand"
    },
    {
      "$ref": "#/$defs/ScanCommand"
    },
    {
      "$ref": "#/$defs/ReportCommand"
    }
  ]
}
```

## POST /predict 요청

```json
{
  "additionalProperties": false,
  "properties": {
    "agent_id": {
      "default": "predator-000",
      "title": "Agent Id",
      "type": "string"
    },
    "observation": {
      "items": {
        "type": "number"
      },
      "maxItems": 26,
      "minItems": 26,
      "title": "Observation",
      "type": "array"
    },
    "policy": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "policy name from GET /policies; default ppo",
      "title": "Policy"
    }
  },
  "required": [
    "observation"
  ],
  "title": "PredictRequest",
  "type": "object"
}
```

## POST /predict 응답

```json
{
  "additionalProperties": false,
  "properties": {
    "action": {
      "title": "Action",
      "type": "string"
    },
    "action_id": {
      "title": "Action Id",
      "type": "integer"
    },
    "policy_version": {
      "title": "Policy Version",
      "type": "string"
    },
    "inference_time_ms": {
      "title": "Inference Time Ms",
      "type": "number"
    }
  },
  "required": [
    "action",
    "action_id",
    "policy_version",
    "inference_time_ms"
  ],
  "title": "PredictResponse",
  "type": "object"
}
```
