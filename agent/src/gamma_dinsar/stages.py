from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# 定义有哪些工作流阶段
STAGE_NAMES: tuple[str, ...] = (
    "preflight",
    "inspect_inputs",
    "import_slc",
    "prepare_dem",
    "coregistration",
    "interferogram",
    "phase_filtering",
    "phase_unwrapping",
    "displacement",
    "geocoding",
    "quality_control",
    "report",
)


@dataclass(frozen=True)
class Stage:
    name: str
    expected_outputs: tuple[str, ...]

    def output_paths(self, task_dir: Path) -> list[Path]:
        return [task_dir / "products" / output for output in self.expected_outputs]


STAGES: tuple[Stage, ...] = (
    Stage("preflight", ("preflight.ok",)),
    Stage("inspect_inputs", ("input_inventory.json",)),
    Stage("import_slc", ("imported_slc.marker",)),
    Stage("prepare_dem", ("prepared_dem.marker",)),
    Stage("coregistration", ("coregistration.marker",)),
    Stage("interferogram", ("interferogram.mock", "coherence.mock")),
    Stage("phase_filtering", ("filtered_phase.mock",)),
    Stage("phase_unwrapping", ("unwrapped_phase.mock",)),
    Stage("displacement", ("los_displacement.mock",)),
    Stage("geocoding", ("geocoded_products.mock",)),
    Stage("quality_control", ("quality_report.json",)),
    Stage("report", ("report.md",)),
)

STAGE_BY_NAME = {stage.name: stage for stage in STAGES}


def stage_index(stage_name: str) -> int:
    try:
        return STAGE_NAMES.index(stage_name)
    except ValueError as exc:
        raise ValueError(f"unknown stage: {stage_name}") from exc
