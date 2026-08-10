from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from .config import BackendSettings, PROJECT_ROOT
from .schemas import (
    ProcessingConfigPreviewResponse,
    ProcessingDefaultGroup,
    ProcessingDefaultParameter,
    ProcessingDefaultsResponse,
    ProcessingFieldInfo,
    ProcessingMissingField,
    ProcessingJobResponse,
    ProcessingTaskResponse,
)
from .processing_workflow import (
    default_field_keys_for_steps,
    resolve_workflow_steps,
    required_field_keys_for_steps,
    workflow_from_inputs,
    workflow_preset_payloads,
    workflow_step_payloads,
    workflow_to_range,
)


AGENT_DEFAULTS_DIR = PROJECT_ROOT / "agent" / "src" / "gamma_dinsar" / "sar_agent"
if str(AGENT_DEFAULTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DEFAULTS_DIR))

from task_defaults import (  # noqa: E402
    CROP_REQUIRED_INPUTS,
    DEFAULT_PARAMETER_GROUPS,
    DEFAULT_TASK_PARAMETERS,
    FIELD_OPTIONS,
    REQUIRED_USER_INPUTS,
    USER_VISIBLE_OPTIONAL_INPUTS,
    minimal_config_template,
    resolve_effective_inputs,
)


SAFETY_NOTICE = "当前接口会生成和保存处理配置；只有显式确认并开启 PROCESSING_EXECUTION_ENABLED=true 后才会提交 Linux worker。"
EXECUTION_NOTICE = "真实处理已开启：后端会在本机 Linux worker 上调用 gamma_dinsar 固定流程。"

BOOL_FIELDS = {
    "enable_crop",
    "skip_unzip",
    "skip_generate_slc",
    "skip_extract_burst",
    "notify_enabled",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safety_notice(settings: BackendSettings | None = None) -> str:
    if settings and settings.processing_execution_enabled:
        return EXECUTION_NOTICE
    return SAFETY_NOTICE


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped.startswith("<") and stripped.endswith(">")


def _normalize_scalar(key: str, value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or _is_placeholder(stripped):
            return None
        if key in BOOL_FIELDS:
            return stripped.lower() in {"1", "true", "yes", "on", "是", "启用"}
        return stripped
    return value


def _normalize_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in inputs.items():
        if key == "env_scripts":
            if isinstance(value, str):
                items = [
                    item.strip()
                    for item in re.split(r"[\n,;]+", value)
                    if item.strip() and not _is_placeholder(item.strip())
                ]
                if items:
                    normalized[key] = items
                continue
            if isinstance(value, list):
                items = [
                    str(item).strip()
                    for item in value
                    if str(item).strip() and not _is_placeholder(str(item).strip())
                ]
                if items:
                    normalized[key] = items
                continue

        cleaned = _normalize_scalar(key, value)
        if cleaned is not None:
            normalized[key] = cleaned
    return normalized


def _dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _field_list(fields: dict[str, str]) -> list[ProcessingFieldInfo]:
    return [
        ProcessingFieldInfo(
            key=key,
            description=description,
            default_value=DEFAULT_TASK_PARAMETERS.get(key),
            options=FIELD_OPTIONS.get(key, []),
        )
        for key, description in fields.items()
    ]


def _field_descriptions() -> dict[str, str]:
    descriptions = {**REQUIRED_USER_INPUTS, **CROP_REQUIRED_INPUTS, **USER_VISIBLE_OPTIONAL_INPUTS}
    descriptions.update(
        {
            "workflow_start": "本次处理的起始步骤。",
            "workflow_end": "本次处理的结束步骤。",
            "workflow_preset": "预设处理范围；留空时使用起止步骤。",
        }
    )
    for group in DEFAULT_PARAMETER_GROUPS.values():
        for key, (_value, description) in group.items():
            descriptions.setdefault(key, description)
    return descriptions


def _step_payloads_for_workflow(workflow: str) -> list[dict[str, Any]]:
    keys = {step.key for step in resolve_workflow_steps(workflow)}
    return [step for step in workflow_step_payloads() if step["key"] in keys]


def _missing_fields(inputs: dict[str, Any], required_field_keys: list[str]) -> list[ProcessingMissingField]:
    descriptions = _field_descriptions()
    return [
        ProcessingMissingField(key=key, description=descriptions.get(key, key))
        for key in required_field_keys
        if not inputs.get(key)
    ]


def _add_unique(target: list[str], key: str) -> None:
    if key not in target:
        target.append(key)


def _workflow_config(
    *,
    template: dict[str, Any],
    normalized: dict[str, Any],
    workflow_start: str,
    workflow_end: str,
    required_field_keys: list[str],
    default_field_keys: list[str],
) -> dict[str, Any]:
    keys: list[str] = []
    for key in ("task_id", "workflow_start", "workflow_end"):
        _add_unique(keys, key)
    for key in [*required_field_keys, *default_field_keys]:
        _add_unique(keys, key)

    config: dict[str, Any] = {}
    for key in keys:
        if key == "workflow_start":
            config[key] = workflow_start
        elif key == "workflow_end":
            config[key] = workflow_end
        elif key in normalized:
            config[key] = normalized[key]
        elif key in template:
            config[key] = template[key]
        elif key in DEFAULT_TASK_PARAMETERS:
            config[key] = DEFAULT_TASK_PARAMETERS[key]
        elif key in CROP_REQUIRED_INPUTS:
            config[key] = f"<{key.upper()}>"

    return config


def get_processing_defaults(settings: BackendSettings) -> ProcessingDefaultsResponse:
    default_groups = [
        ProcessingDefaultGroup(
            name=group_name,
            parameters=[
                ProcessingDefaultParameter(key=key, default_value=value, description=description)
                if key not in FIELD_OPTIONS
                else ProcessingDefaultParameter(
                    key=key,
                    default_value=value,
                    description=description,
                    options=FIELD_OPTIONS[key],
                )
                for key, (value, description) in parameters.items()
            ],
        )
        for group_name, parameters in DEFAULT_PARAMETER_GROUPS.items()
    ]
    template = minimal_config_template()

    return ProcessingDefaultsResponse(
        execution_enabled=settings.processing_execution_enabled,
        safety_notice=_safety_notice(settings),
        required_inputs=_field_list(REQUIRED_USER_INPUTS),
        crop_inputs=_field_list(CROP_REQUIRED_INPUTS),
        visible_optional_inputs=_field_list(USER_VISIBLE_OPTIONAL_INPUTS),
        default_groups=default_groups,
        processing_steps=workflow_step_payloads(),
        workflow_presets=workflow_preset_payloads(),
        minimal_template=template,
        minimal_template_yaml=_dump_yaml(template),
    )


def preview_processing_config(settings: BackendSettings, inputs: dict[str, Any]) -> ProcessingConfigPreviewResponse:
    normalized = _normalize_inputs(inputs)
    template = minimal_config_template()
    workflow_seed = dict(template)
    workflow_seed.update(normalized)
    workflow = workflow_from_inputs(workflow_seed)
    workflow_start, workflow_end = workflow_to_range(workflow)
    selected_steps = resolve_workflow_steps(workflow)
    effective_parameters = resolve_effective_inputs(normalized)
    required_field_keys = required_field_keys_for_steps(selected_steps, effective_parameters)
    default_field_keys = default_field_keys_for_steps(selected_steps, effective_parameters)
    missing = _missing_fields(effective_parameters, required_field_keys)
    config = _workflow_config(
        template=template,
        normalized=normalized,
        workflow_start=workflow_start,
        workflow_end=workflow_end,
        required_field_keys=required_field_keys,
        default_field_keys=default_field_keys,
    )

    return ProcessingConfigPreviewResponse(
        status="needs_input" if missing else "ready",
        missing=missing,
        config=config,
        effective_parameters=effective_parameters,
        config_yaml=_dump_yaml(config),
        workflow=workflow,
        workflow_start=workflow_start,
        workflow_end=workflow_end,
        selected_steps=_step_payloads_for_workflow(workflow),
        required_field_keys=required_field_keys,
        execution_enabled=settings.processing_execution_enabled,
        safety_notice=_safety_notice(settings),
    )


def _safe_task_id(raw_task_id: Any) -> str:
    value = str(raw_task_id or "").strip()
    if not value or value == "example_task" or _is_placeholder(value):
        value = f"gamma-task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-")
    return safe or f"gamma-task-{uuid4().hex[:8]}"


def _unique_task_dir(base_dir: Path, task_id: str) -> tuple[str, Path]:
    candidate_id = task_id
    candidate_dir = base_dir / candidate_id
    suffix = 2
    while candidate_dir.exists():
        candidate_id = f"{task_id}-{suffix}"
        candidate_dir = base_dir / candidate_id
        suffix += 1
    return candidate_id, candidate_dir


def create_processing_task(settings: BackendSettings, inputs: dict[str, Any]) -> ProcessingTaskResponse:
    preview = preview_processing_config(settings, inputs)
    task_id, task_dir = _unique_task_dir(
        settings.processing_tasks_dir,
        _safe_task_id(preview.config.get("task_id")),
    )
    task_dir.mkdir(parents=True, exist_ok=False)

    config_path = task_dir / "task.yaml"
    metadata_path = task_dir / "task.json"
    config_path.write_text(preview.config_yaml, encoding="utf-8")

    status = "pending_review" if preview.missing else "ready_for_linux_worker"
    metadata = {
        "task_id": task_id,
        "status": status,
        "created_at": _utc_now(),
        "execution_enabled": settings.processing_execution_enabled,
        "safety_notice": _safety_notice(settings),
        "missing": [field.model_dump() for field in preview.missing],
        "workflow": preview.workflow,
        "workflow_start": preview.workflow_start,
        "workflow_end": preview.workflow_end,
        "selected_steps": [step.model_dump() for step in preview.selected_steps],
        "required_field_keys": preview.required_field_keys,
        "config_path": str(config_path),
        "metadata_path": str(metadata_path),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return ProcessingTaskResponse(
        task_id=task_id,
        status=status,
        task_dir=str(task_dir),
        config_path=str(config_path),
        metadata_path=str(metadata_path),
        missing=preview.missing,
        config_yaml=preview.config_yaml,
        workflow=preview.workflow,
        workflow_start=preview.workflow_start,
        workflow_end=preview.workflow_end,
        selected_steps=preview.selected_steps,
        required_field_keys=preview.required_field_keys,
        execution_enabled=settings.processing_execution_enabled,
        safety_notice=_safety_notice(settings),
    )


def read_processing_task(settings: BackendSettings, task_id: str) -> ProcessingTaskResponse | None:
    safe_id = _safe_task_id(task_id)
    task_dir = settings.processing_tasks_dir / safe_id
    metadata_path = task_dir / "task.json"
    config_path = task_dir / "task.yaml"

    if not metadata_path.exists() or not config_path.exists():
        return None

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    missing = [ProcessingMissingField(**field) for field in metadata.get("missing", [])]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    workflow = metadata.get("workflow") or workflow_from_inputs(config)
    workflow_start, workflow_end = workflow_to_range(workflow)
    selected_steps = metadata.get("selected_steps") or _step_payloads_for_workflow(workflow)
    required_field_keys = metadata.get("required_field_keys") or required_field_keys_for_steps(
        resolve_workflow_steps(workflow),
        resolve_effective_inputs(_normalize_inputs(config)),
    )

    return ProcessingTaskResponse(
        task_id=metadata["task_id"],
        status=metadata["status"],
        task_dir=str(task_dir),
        config_path=str(config_path),
        metadata_path=str(metadata_path),
        missing=missing,
        config_yaml=config_path.read_text(encoding="utf-8"),
        workflow=workflow,
        workflow_start=workflow_start,
        workflow_end=workflow_end,
        selected_steps=selected_steps,
        required_field_keys=required_field_keys,
        execution_enabled=metadata.get("execution_enabled", settings.processing_execution_enabled),
        safety_notice=metadata.get("safety_notice", _safety_notice(settings)),
    )


def _task_dir_from_id(settings: BackendSettings, task_id: str) -> Path:
    safe_id = _safe_task_id(task_id)
    return settings.processing_tasks_dir / safe_id


def _job_status_path(task_dir: Path, job_id: str) -> Path:
    return task_dir / "jobs" / job_id / "job.json"


def _tail_text(path: Path, max_chars: int = 5000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _read_job(settings: BackendSettings, job_path: Path) -> ProcessingJobResponse:
    data = json.loads(job_path.read_text(encoding="utf-8"))
    log_path = Path(data["log_path"])
    data["log_tail"] = _tail_text(log_path)
    data["execution_enabled"] = settings.processing_execution_enabled
    data["safety_notice"] = _safety_notice(settings)
    return ProcessingJobResponse(**data)


def _resolved_workflow_for_task(task: ProcessingTaskResponse, workflow: str) -> str:
    if workflow and workflow != "configured":
        workflow_to_range(workflow)
        return workflow
    return task.workflow


def _missing_for_task_workflow(task: ProcessingTaskResponse, workflow: str) -> list[ProcessingMissingField]:
    effective = _effective_inputs_for_task(task)
    required_keys = required_field_keys_for_steps(resolve_workflow_steps(workflow), effective)
    return _missing_fields(effective, required_keys)


def _effective_inputs_for_task(task: ProcessingTaskResponse) -> dict[str, Any]:
    config = yaml.safe_load(Path(task.config_path).read_text(encoding="utf-8")) or {}
    return resolve_effective_inputs(_normalize_inputs(config))


def _job_log_path_for_task(task: ProcessingTaskResponse, job_id: str) -> Path:
    effective = _effective_inputs_for_task(task)
    task_root = effective.get("task_root")
    if task_root:
        return Path(str(task_root)).expanduser() / "logs" / "processing_jobs" / job_id / "job.log"
    return Path(task.task_dir) / "jobs" / job_id / "job.log"


def create_processing_job(settings: BackendSettings, task_id: str, workflow: str = "configured") -> ProcessingJobResponse:
    if not settings.processing_execution_enabled:
        raise RuntimeError("真实处理未开启：请在后端环境变量中设置 PROCESSING_EXECUTION_ENABLED=true 后重启 FastAPI。")

    task = read_processing_task(settings, task_id)
    if task is None:
        raise FileNotFoundError("processing task not found")

    resolved_workflow = _resolved_workflow_for_task(task, workflow)
    missing_fields = _missing_for_task_workflow(task, resolved_workflow)
    if missing_fields:
        missing = ", ".join(field.key for field in missing_fields)
        raise ValueError(f"配置仍有缺失字段，不能开始处理：{missing}")

    task_dir = Path(task.task_dir)
    job_id = f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    job_dir = task_dir / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    job_path = job_dir / "job.json"
    log_path = _job_log_path_for_task(task, job_id)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    job_data: dict[str, Any] = {
        "job_id": job_id,
        "task_id": task.task_id,
        "status": "queued",
        "workflow": resolved_workflow,
        "progress_current": 0,
        "progress_total": 0,
        "progress_percent": 0,
        "current_step": None,
        "steps": [],
        "config_path": task.config_path,
        "job_path": str(job_path),
        "log_path": str(log_path),
        "pid": None,
        "return_code": None,
        "error": None,
        "log_tail": "",
        "created_at": _utc_now(),
        "started_at": None,
        "finished_at": None,
        "execution_enabled": settings.processing_execution_enabled,
        "safety_notice": _safety_notice(settings),
    }
    job_path.write_text(json.dumps(job_data, ensure_ascii=False, indent=2), encoding="utf-8")

    command = [
        sys.executable,
        "-m",
        "backend.processing_worker",
        "--job-path",
        str(job_path),
        "--config-path",
        task.config_path,
        "--log-path",
        str(log_path),
        "--workflow",
        resolved_workflow,
    ]

    log_handle = log_path.open("a", encoding="utf-8")
    popen_kwargs: dict[str, Any] = {
        "cwd": str(PROJECT_ROOT),
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "text": True,
    }
    if os.name != "nt":
        popen_kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **popen_kwargs)
    log_handle.close()

    job_data["pid"] = process.pid
    job_path.write_text(json.dumps(job_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return _read_job(settings, job_path)


def read_processing_job(settings: BackendSettings, task_id: str, job_id: str) -> ProcessingJobResponse | None:
    job_path = _job_status_path(_task_dir_from_id(settings, task_id), job_id)
    if not job_path.exists():
        return None
    return _read_job(settings, job_path)


def cancel_processing_job(settings: BackendSettings, task_id: str, job_id: str) -> ProcessingJobResponse:
    job_path = _job_status_path(_task_dir_from_id(settings, task_id), job_id)
    if not job_path.exists():
        raise FileNotFoundError("processing job not found")

    data = json.loads(job_path.read_text(encoding="utf-8"))
    if data.get("status") not in {"queued", "running", "cancel_requested"}:
        return _read_job(settings, job_path)

    pid = data.get("pid")
    data["status"] = "cancel_requested"
    data["finished_at"] = data.get("finished_at") or _utc_now()
    data["error"] = "用户请求停止处理任务。"
    job_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if pid:
        try:
            if os.name != "nt":
                os.killpg(int(pid), signal.SIGTERM)
            else:
                os.kill(int(pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as exc:
            data["error"] = f"停止任务时出错：{exc}"

    data["status"] = "cancelled"
    data["finished_at"] = _utc_now()
    job_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return _read_job(settings, job_path)
