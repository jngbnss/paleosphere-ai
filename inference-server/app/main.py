"""FastAPI sim/inference server.

    uv run python -m app            # http://127.0.0.1:8790
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.policies import PolicyRegistry
from app.schemas import (
    CLIENT_POLICY,
    MAPS,
    ActionCommand,
    ErrorMessage,
    ExplorerMoveCommand,
    FieldReport,
    Hello,
    PauseCommand,
    PolicyInfo,
    PredictRequest,
    PredictResponse,
    ReportCommand,
    ResumeCommand,
    ScanCommand,
    ScanResult,
    SetSpeedCommand,
    StartCommand,
    StepCommand,
    control_adapter,
)
from app.session import ClientPolicy, SimSession
from paleosphere.policies import PredatorAction

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="PaleoSphere sim server", version="0.1.0")
registry = PolicyRegistry()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "policies": registry.names}


@app.get("/policies", response_model=list[PolicyInfo])
def policies() -> list[PolicyInfo]:
    return registry.info()


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    name = req.policy or "ppo"
    try:
        policy = registry.get(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not hasattr(policy, "predict"):
        raise HTTPException(status_code=400, detail=f"policy {name!r} needs world state, use ppo")
    started = time.perf_counter()
    action = policy.predict(np.asarray(req.observation, dtype=np.float32))
    elapsed_ms = (time.perf_counter() - started) * 1000
    return PredictResponse(
        action=PredatorAction(action).name,
        action_id=action,
        policy_version=policy.metadata().get("version") or policy.name,
        inference_time_ms=round(elapsed_ms, 3),
    )


@app.get("/")
def web_viewer() -> FileResponse:
    """Minimal browser viewer (fallback when Godot is not installed)."""
    return FileResponse(STATIC_DIR / "viewer.html")


@app.websocket("/ws/sim")
async def ws_sim(ws: WebSocket) -> None:
    await ws.accept()
    await ws.send_text(
        Hello(
            policies=registry.names, maps=list(MAPS), herbivore_policies=registry.herd_names
        ).model_dump_json()
    )
    state: dict[str, SimSession | None] = {"session": None}
    wake = asyncio.Event()
    send_lock = asyncio.Lock()

    async def send(model) -> None:
        async with send_lock:
            await ws.send_text(model.model_dump_json())

    async def runner() -> None:
        loop = asyncio.get_running_loop()
        while True:
            session = state["session"]
            if session is None or session.paused or not session.ready:
                await wake.wait()
                wake.clear()
                continue
            started = loop.time()
            session.step()
            await send(session.snapshot())
            delay = 1.0 / session.ticks_per_second - (loop.time() - started)
            if delay > 0:
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(wake.wait(), timeout=delay)
                wake.clear()

    task = asyncio.create_task(runner())
    try:
        while True:
            raw = await ws.receive_text()
            try:
                cmd = control_adapter.validate_json(raw)
            except ValidationError as exc:
                await send(ErrorMessage(message=f"invalid command: {exc.errors()[0]['msg']}"))
                continue
            session = state["session"]
            if isinstance(cmd, StartCommand):
                try:
                    policy = (
                        ClientPolicy()
                        if cmd.predator_policy == CLIENT_POLICY
                        else registry.get(cmd.predator_policy)
                    )
                    herd_policy = registry.get_herd(cmd.herbivore_policy)
                except KeyError as exc:
                    await send(ErrorMessage(message=str(exc)))
                    continue
                try:
                    session = SimSession(cmd, policy, herd_policy)
                except ValueError as exc:
                    await send(ErrorMessage(message=str(exc)))
                    continue
                state["session"] = session
                await send(session.snapshot())
            elif session is None:
                await send(ErrorMessage(message="send a start command first"))
                continue
            elif isinstance(cmd, PauseCommand):
                session.paused = True
                await send(session.snapshot())
            elif isinstance(cmd, ResumeCommand):
                session.paused = False
            elif isinstance(cmd, SetSpeedCommand):
                session.ticks_per_second = cmd.ticks_per_second
            elif isinstance(cmd, ExplorerMoveCommand | ScanCommand | ReportCommand):
                journal = session.journal
                if journal is None:
                    await send(ErrorMessage(message="start with explorer: true first"))
                    continue
                if isinstance(cmd, ExplorerMoveCommand):
                    journal.move_to(cmd.x, cmd.z)
                    if session.paused or session.done:
                        await send(session.snapshot())  # show the move while time stands still
                elif isinstance(cmd, ScanCommand):
                    w = session.world
                    await send(ScanResult(
                        tick=w.tick, position=tuple(map(float, journal.position)),
                        radius=journal.scan_radius, sightings=journal.scan(w),
                    ))
                else:
                    w = session.world
                    await send(FieldReport(tick=w.tick, markdown=journal.report(w),
                                           stats=journal.stats(w)))
                continue
            elif isinstance(cmd, ActionCommand):
                error = session.set_client_action(cmd.tick, cmd.action)
                if error:
                    await send(ErrorMessage(message=error))
                    continue
            elif isinstance(cmd, StepCommand):
                if session.client_mode:
                    await send(ErrorMessage(message="client mode advances on `action`, not `step`"))
                    continue
                for _ in range(cmd.n):
                    session.step()
                await send(session.snapshot())
            wake.set()
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
