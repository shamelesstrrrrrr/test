from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from gamma_dinsar.stages import STAGE_NAMES


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StageStatus = StageStatus.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None
    log_file: str | None = None


class TaskState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    stages: dict[str, StageRecord] = Field(default_factory=dict)

    @classmethod
    def new(cls, task_id: str) -> "TaskState":
        return cls(task_id=task_id, stages={name: StageRecord() for name in STAGE_NAMES})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, output_dir: Path, task_id: str) -> None:
        self.task_dir = output_dir / task_id
        self.state_path = self.task_dir / "state.json"
        self.task_id = task_id

    def load_or_create(self) -> TaskState:
        if self.state_path.exists():
            with self.state_path.open("r", encoding="utf-8") as handle:
                return TaskState.model_validate(json.load(handle))
        return TaskState.new(self.task_id)

    def save(self, state: TaskState) -> None:
        self.task_dir.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as handle:
            json.dump(state.model_dump(mode="json"), handle, indent=2)

    def mark(
        self,
        state: TaskState,
        stage_name: str,
        status: StageStatus,
        *,
        message: str | None = None,
        log_file: str | None = None,
    ) -> None:
        record = state.stages[stage_name]
        now = utc_now()
        if status == StageStatus.RUNNING:
            record.started_at = now
            record.finished_at = None
        elif status in {StageStatus.SUCCESS, StageStatus.FAILED, StageStatus.SKIPPED}:
            record.finished_at = now
        record.status = status
        record.message = message
        if log_file is not None:
            record.log_file = log_file
        self.save(state)
