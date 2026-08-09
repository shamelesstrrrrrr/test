from __future__ import annotations

from pathlib import Path
from typing import Any

from src.gamma_dinsar.beiy.command_specs import (
    POLARIZATION_OPTIONS,
    SATELLITE_OPTIONS,
    SWATH_OPTIONS,
    normalize_option,
)
from src.gamma_dinsar.sar_agent.stage_specs import S1_PREPROCESSING_STAGES
from src.gamma_dinsar.sar_agent.state import StageRuntimeState, WorkflowState, now

DEFAULT_INPUTS = {
    "polarization": "VV",
    "polarization_code": "0",
    "range_looks": 1,
    "azimuth_looks": 1,
    "lat_ov": 5,
    "lon_ov": 5,
    "data_format": "-",
    "scale_factor": "-",
}

DERIVED_PATH_TEMPLATES = {
    "slc_dir": "{work_dir}/SLC",
    "unzip_slc_dir": "{work_dir}/SLC",
    "burst_dir": "{work_dir}/SLC_select",
    "s1_slc_dir": "{work_dir}/SLC_select",
    "geo_dir": "{work_dir}/GEO",
    "rslc_dir": "{work_dir}/RSLC",
    "date_list": "{work_dir}/SLC_select/list",
    "list_file": "{work_dir}/SLC_select/list",
    "slc_file": "{work_dir}/SLC_select/{master_date}.slc",
}

STARTUP_REQUIRED_INPUTS = [
    "task_id",
    "raw_zip_dir",
    "satellite_code",
    "swath_code",
    # "pod_dir",
    # "dem_file",
    # "master_date",
    # "bn_start",
    # "bn_end",
]


class S1PreprocessingWorkflow:
    def __init__(self) -> None:
        self.state = WorkflowState()
        self.state.inputs.update(DEFAULT_INPUTS)
        self.state.stages = {
            stage.name: StageRuntimeState()
            for stage in S1_PREPROCESSING_STAGES
        }

    def update_inputs(self, **kwargs: Any) -> str:
        try:
            normalized = self._normalize_inputs(kwargs)
        except ValueError as exc:
            return str(exc)

        clean = {k: v for k, v in normalized.items() if v is not None and v != ""}
        self.state.inputs.update(clean)
        self._apply_derived_inputs()
        self.state.task_id = self.state.inputs.get("task_id")
        self.state.touch()

        missing = self.missing_startup_inputs()
        if missing:
            return "已更新任务信息。\n当前还缺少：" + ", ".join(missing)
        return "任务启动参数已完整，可以运行Mock流程。"

    def validate(self) -> str:
        missing = self.missing_startup_inputs()
        if missing:
            return "任务信息不完整，还缺少：" + ", ".join(missing)
        return "任务启动参数完整。"

    def missing_startup_inputs(self) -> list[str]:
        return [key for key in STARTUP_REQUIRED_INPUTS if not self.state.inputs.get(key)]

    def run_mock(self) -> str:
        startup_missing = self.missing_startup_inputs()
        if startup_missing:
            self.state.status = "waiting"
            return "不能运行Mock流程，还缺少：" + ", ".join(startup_missing)

        messages = []
        for index, stage in enumerate(S1_PREPROCESSING_STAGES):
            self.state.current_stage_index = index
            runtime = self.state.stages[stage.name]

            missing = self._missing_for_stage(stage.required_inputs)
            if missing:
                runtime.status = "waiting"
                runtime.missing_inputs = missing
                runtime.message = "缺少阶段参数"
                self.state.status = "waiting"
                self.state.touch()
                return f"阶段【{stage.title}】缺少参数：" + ", ".join(missing)

            runtime.status = "running"
            runtime.started_at = now()
            runtime.used_inputs = {key: self.state.inputs.get(key) for key in stage.required_inputs}
            self.state.touch()

            product_dir = self._product_dir()
            product_dir.mkdir(parents=True, exist_ok=True)
            marker = product_dir / f"{stage.name}.mock"
            marker.write_text(
                f"Mock output for {stage.name}. No real GAMMA command was executed.\n",
                encoding="utf-8",
            )

            runtime.status = "success"
            runtime.finished_at = now()
            runtime.message = "Mock阶段完成，未执行真实GAMMA命令"
            runtime.missing_inputs = []
            messages.append(f"{stage.title}: success")

        self.state.status = "success"
        self.state.touch()
        return "Mock流程完成：\n" + "\n".join(messages)

    def status(self) -> dict[str, Any]:
        return {
            "task_id": self.state.task_id,
            "status": self.state.status,
            "current_stage_index": self.state.current_stage_index,
            "inputs": dict(self.state.inputs),
            "stages": {
                name: vars(stage_state)
                for name, stage_state in self.state.stages.items()
            },
            "updated_at": self.state.updated_at,
        }

    def _normalize_inputs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(kwargs)

        if "satellite" in normalized:
            satellite = normalized.pop("satellite")
            normalized["satellite"] = satellite
            normalized["satellite_code"] = normalize_option(str(satellite), SATELLITE_OPTIONS, "卫星类型")

        if "polarization" in normalized:
            polarization = normalized["polarization"]
            normalized["polarization_code"] = normalize_option(str(polarization), POLARIZATION_OPTIONS, "极化方式")

        if "swath" in normalized:
            swath = normalized.pop("swath")
            normalized["swath"] = swath
            normalized["swath_code"] = normalize_option(str(swath), SWATH_OPTIONS, "swath")

        if "burst_start" in normalized:
            normalized["bn_start"] = normalized.pop("burst_start")

        if "burst_end" in normalized:
            normalized["bn_end"] = normalized.pop("burst_end")

        if "opod_dir" in normalized:
            normalized["pod_dir"] = normalized.pop("opod_dir")

        return normalized

    def _apply_derived_inputs(self) -> None:
        for key, template in DERIVED_PATH_TEMPLATES.items():
            if self.state.inputs.get(key):
                continue
            try:
                self.state.inputs[key] = str(Path(template.format(**self.state.inputs)))
            except KeyError:
                continue

    def _missing_for_stage(self, required_inputs: list[str]) -> list[str]:
        return [key for key in required_inputs if not self.state.inputs.get(key)]

    def _product_dir(self) -> Path:
        work_dir = self.state.inputs.get("work_dir") or "."
        task_id = self.state.inputs.get("task_id") or "unnamed_task"
        return Path(work_dir) / "mock_outputs" / task_id