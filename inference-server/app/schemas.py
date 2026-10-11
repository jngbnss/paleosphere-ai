"""Wire protocol between the Python sim server and the Godot viewer.

Server -> client: `Snapshot` (every tick while running) and `ServerMessage` variants.
Client -> server: `ControlCommand` (discriminated by `type`).
JSON Schemas are exported to docs/protocol.md by `python -m app.export_schema`.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from paleosphere.policies.observation import OBS_DIM

PROTOCOL_VERSION = 1
# `start.predator_policy` value that hands predator decisions to the viewer (Godot in-engine
# inference): snapshots then carry the predator observation and the sim waits for `action`.
CLIENT_POLICY = "client"
MAPS = ("map_a", "map_b", "ecosystem")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------- world state
class DinoState(_Model):
    agent_id: str
    species: Literal["herbivore", "predator"]
    position: tuple[float, float]
    velocity: tuple[float, float]
    health: float
    energy: float
    hunger: float
    thirst: float
    age: int
    current_action: str
    target_id: str | None
    alive: bool
    death_cause: str | None
    status_code: str
    status_label: str
    vision: float
    # ecosystem map (reproduction) only
    generation: int | None = None
    parent_id: str | None = None
    breed_cooldown: int | None = None


class PlantState(_Model):
    plant_id: str
    position: tuple[float, float]
    radius: float
    food: float


class WaterState(_Model):
    water_id: str
    position: tuple[float, float]
    radius: float


class RockState(_Model):
    rock_id: str
    position: tuple[float, float]
    radius: float


class EventState(_Model):
    tick: int
    kind: str
    agent_id: str
    target_id: str | None
    data: dict


class Metrics(_Model):
    herbivores_alive: int
    predator_energy: float  # tracked predator (predator-000)
    predator_hunger: float
    kills: int  # by every predator
    attack_attempts: int  # tracked predator
    invalid_attacks: int
    predators_alive: int = 1
    births: int = 0  # cumulative, ecosystem map only


class ExplorerState(_Model):
    position: tuple[float, float]
    scan_radius: float
    view_radius: float
    scans: int
    identified: int
    explored_fraction: float
    explored: list[list[bool]] = Field(description="GRID x GRID cells, [x][z]")


class Snapshot(_Model):
    type: Literal["snapshot"] = "snapshot"
    protocol_version: int = PROTOCOL_VERSION
    tick: int
    seed: int
    map: str
    map_size: float
    is_night: bool
    predator_policy: str
    herbivore_policy: str = "rule"
    paused: bool
    ticks_per_second: float
    done: bool
    dinos: list[DinoState]
    plants: list[PlantState]
    waters: list[WaterState]
    rocks: list[RockState]
    events: list[EventState]
    metrics: Metrics
    explorer: ExplorerState | None = Field(None, description="explorer mode only")
    predator_observation: list[float] | None = Field(
        None,
        description=f"client mode only: the {OBS_DIM}-dim predator observation at this tick; "
        "reply with an `action` command for the same tick",
    )


class Sighting(_Model):
    agent_id: str
    species: Literal["herbivore", "predator"]
    position: tuple[float, float]
    distance: float
    alive: bool
    status_label: str
    current_action: str
    health: float
    energy: float
    hunger: float
    thirst: float
    new: bool = Field(description="first time this individual is identified")


class ScanResult(_Model):
    type: Literal["scan_result"] = "scan_result"
    tick: int
    position: tuple[float, float]
    radius: float
    sightings: list[Sighting]


class FieldReport(_Model):
    type: Literal["report"] = "report"
    tick: int
    markdown: str
    stats: dict


class ErrorMessage(_Model):
    type: Literal["error"] = "error"
    message: str


class Hello(_Model):
    type: Literal["hello"] = "hello"
    protocol_version: int = PROTOCOL_VERSION
    policies: list[str]
    maps: list[str]
    herbivore_policies: list[str] = ["rule"]


# ------------------------------------------------------------------ client commands
class StartCommand(_Model):
    type: Literal["start"]
    seed: int = 10000
    map: Literal["map_a", "map_b", "ecosystem"] = "map_a"
    predator_policy: str = "rule"
    herbivore_policy: str = Field("rule", description="rule | random | herd-<name> model")
    explorer: bool = Field(False, description="explorer mode: a field researcher at map center")
    ticks_per_second: float = Field(10.0, gt=0, le=200)


class PauseCommand(_Model):
    type: Literal["pause"]


class ResumeCommand(_Model):
    type: Literal["resume"]


class SetSpeedCommand(_Model):
    type: Literal["set_speed"]
    ticks_per_second: float = Field(gt=0, le=200)


class StepCommand(_Model):
    type: Literal["step"]
    n: int = Field(1, ge=1, le=1000)


class ActionCommand(_Model):
    """Client mode: the predator action for `tick` (the tick of the snapshot it answers)."""

    type: Literal["action"]
    tick: int = Field(ge=0)
    action: int = Field(ge=0, le=6, description="PredatorAction id")


class ExplorerMoveCommand(_Model):
    """Explorer mode: walk to (x, z) (clamped to the map). Does not affect the simulation."""

    type: Literal["explorer_move"]
    x: float
    z: float


class ScanCommand(_Model):
    type: Literal["scan"]


class ReportCommand(_Model):
    type: Literal["report"]


ControlCommand = Annotated[
    StartCommand | PauseCommand | ResumeCommand | SetSpeedCommand | StepCommand | ActionCommand
    | ExplorerMoveCommand | ScanCommand | ReportCommand,
    Field(discriminator="type"),
]
control_adapter: TypeAdapter[ControlCommand] = TypeAdapter(ControlCommand)


# ------------------------------------------------------------------------- predict
class PredictRequest(_Model):
    agent_id: str = "predator-000"
    observation: list[float] = Field(min_length=OBS_DIM, max_length=OBS_DIM)
    policy: str | None = Field(None, description="policy name from GET /policies; default ppo")


class PredictResponse(_Model):
    action: str
    action_id: int
    policy_version: str
    inference_time_ms: float


class PolicyInfo(_Model):
    name: str
    kind: str
    version: str | None = None
    model_sha256: str | None = None
