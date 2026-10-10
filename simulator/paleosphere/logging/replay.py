"""JSON Lines replay: line 1 is a header, then one snapshot per recorded tick.

The same snapshot format is streamed by the sim server and rendered by the Godot viewer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import IO

from paleosphere.core.events import Event
from paleosphere.core.world import World

REPLAY_VERSION = 1


class ReplayWriter:
    def __init__(self, path: Path, every: int = 1, metadata: dict | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.every = max(1, every)
        self.metadata = metadata or {}
        self._fh: IO[str] | None = None

    def __enter__(self) -> ReplayWriter:
        self._fh = self.path.open("w", encoding="utf-8", newline="\n")
        return self

    def __exit__(self, *exc) -> None:
        if self._fh:
            self._fh.close()

    def __call__(self, world: World, events: list[Event]) -> None:
        assert self._fh is not None, "use ReplayWriter as a context manager"
        if world.tick == 0:
            header = {
                "type": "header",
                "version": REPLAY_VERSION,
                "map_size": world.size,
                "every": self.every,
                **self.metadata,
            }
            self._fh.write(json.dumps(header) + "\n")
        if world.tick % self.every == 0 or world.done:
            frame = {
                "type": "frame",
                "snapshot": world.to_snapshot(),
                "events": [e.to_dict() for e in events],
            }
            self._fh.write(json.dumps(frame) + "\n")


def read_replay(path: Path) -> tuple[dict, list[dict]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    frames = [json.loads(line) for line in lines[1:] if line]
    return header, frames
