from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Polarization(str, Enum):
    VV = "VV"
    VH = "VH"
    HH = "HH"
    HV = "HV"


class MockScenario(str, Enum):
    SUCCESS = "success"
    COMMAND_FAILURE = "command_failure"
    TIMEOUT = "timeout"
    MISSING_OUTPUT = "missing_output"


class MockConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: MockScenario = MockScenario.SUCCESS
    fail_stage: str | None = None


class TaskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.-]+$")
    master_slc: Path
    slave_slc: Path
    aoi: Path
    dem: Path
    polarization: Polarization = Polarization.VV
    output_dir: Path
    resume: bool = False
    mock: MockConfig = Field(default_factory=MockConfig)

    @field_validator("master_slc", "slave_slc", "aoi", "dem", "output_dir", mode="before")
    @classmethod
    def non_empty_path(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("path must not be empty")
        return value


def load_task_config(path: Path) -> TaskConfig:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return TaskConfig.model_validate(data)
