"""
FastAPI server exposing the IncidentCommanderEnv via HTTP.

Endpoints:
  POST /reset       — Reset environment (body: {"task_id": "easy"})
  POST /step        — Take an action (body: Action JSON)
  GET  /state       — Get current state
  GET  /tasks       — List available tasks
  GET  /grade       — Get episode score
  GET  /health      — Health check

CRITICAL: POST /reset with empty body {} must return 200.
The validator sends exactly this to check if the Space is alive.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.environment import IncidentCommanderEnv
from app.models import Action, EnvironmentState, Observation, Reward

app = FastAPI(
    title="Incident Commander OpenEnv",
    description="OpenEnv environment for training/evaluating AI agents on infrastructure incident response.",
    version="1.0.0",
)

# Single environment instance per container
env = IncidentCommanderEnv()


# ── Request/Response schemas ─────────────────────────────────────────────────

class ResetRequest(BaseModel):
    task_id: str = "easy"  # DEFAULT VALUE — validator sends {} which must work


class StepResponse(BaseModel):
    observation: Observation
    reward: Reward
    done: bool
    info: dict


class GradeResponse(BaseModel):
    task_id: str
    score: float
    steps_taken: int


class TaskInfo(BaseModel):
    task_id: str
    description: str
    num_phases: int


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "environment": "incident-commander", "version": "1.0.0"}


@app.post("/reset", response_model=Observation)
def reset(req: ResetRequest = ResetRequest()):
    """Reset the environment. Accepts empty body {} (defaults to easy task)."""
    try:
        obs = env.reset(task_id=req.task_id)
        return obs
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/step", response_model=StepResponse)
def step(action: Action):
    try:
        obs, reward, done, info = env.step(action)
        return StepResponse(observation=obs, reward=reward, done=done, info=info)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/state", response_model=EnvironmentState)
def get_state():
    try:
        return env.state()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/tasks", response_model=list[TaskInfo])
def list_tasks():
    from app.environment import TASK_DESCRIPTIONS, TASK_GENERATORS

    tasks = []
    for tid, gen in TASK_GENERATORS.items():
        phases, _ = gen()
        tasks.append(TaskInfo(
            task_id=tid,
            description=TASK_DESCRIPTIONS[tid],
            num_phases=len(phases),
        ))
    return tasks


@app.get("/grade", response_model=GradeResponse)
def grade():
    try:
        s = env.state()
        score = env.grade()
        return GradeResponse(task_id=s.task_id, score=score, steps_taken=s.step_count)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
