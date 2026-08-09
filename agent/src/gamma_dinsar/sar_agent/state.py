from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

StageStatus = Literal["pending", "waiting", "running", "success", "failed", "skipped"]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class StageRuntimeState:
    status: StageStatus = "pending"
    missing_inputs: list[str] = field(default_factory=list)
    used_inputs: dict[str, Any] = field(default_factory=dict)
    log_file: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None


@dataclass
class WorkflowState:
    task_id: str | None = None
    current_stage_index: int = 0
    status: StageStatus = "pending"
    inputs: dict[str, Any] = field(default_factory=dict)
    stages: dict[str, StageRuntimeState] = field(default_factory=dict)
    updated_at: str | None = None

    def touch(self) -> None:
        self.updated_at = now()