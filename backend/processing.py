from __future__ import annotations

import json
import re
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
    ProcessingTaskResponse,
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
    missing_required_inputs,
    resolve_effective_inputs,
)


EXECUTION_ENABLED = False
SAFETY_NOTICE = (
    "当前接口只生成和保存处理配置，不执行 GAMMA、不执行 Shell、不连接 SSH。"
    "真实处理应部署在安装了 GAMMA 的 Linux worker 上。"
)

BOOL_FIELDS = {
    "enable_crop",
    "skip_unzip",
    "skip_generate_slc",
    "skip_extract_burst",
    "notify_enabled",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
                items = [item.strip() for item in re.split(r"[\n,;]+", value) if item.strip()]
                if items:
                    normalized[key] = items
                continue
            if isinstance(value, list):
                items = [str(item).strip() for item in value if str(item).strip()]
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


def _missing_fields(inputs: dict[str, Any]) -> list[ProcessingMissingField]:
    descriptions = {**REQUIRED_USER_INPUTS, **CROP_REQUIRED_INPUTS}
    return [
        ProcessingMissingField(key=key, description=descriptions[key])
        for key in missing_required_inputs(inputs)
    ]


def get_processing_defaults() -> ProcessingDefaultsResponse:
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
        safety_notice=SAFETY_NOTICE,
        required_inputs=_field_list(REQUIRED_USER_INPUTS),
        crop_inputs=_field_list(CROP_REQUIRED_INPUTS),
        visible_optional_inputs=_field_list(USER_VISIBLE_OPTIONAL_INPUTS),
        default_groups=default_groups,
        minimal_template=template,
        minimal_template_yaml=_dump_yaml(template),
    )


def preview_processing_config(inputs: dict[str, Any]) -> ProcessingConfigPreviewResponse:
    normalized = _normalize_inputs(inputs)
    template = minimal_config_template()
    config = dict(template)

    for key, value in normalized.items():
        config[key] = value

    effective_parameters = resolve_effective_inputs(normalized)
    missing = _missing_fields(normalized)

    return ProcessingConfigPreviewResponse(
        status="needs_input" if missing else "ready",
        missing=missing,
        config=config,
        effective_parameters=effective_parameters,
        config_yaml=_dump_yaml(config),
        safety_notice=SAFETY_NOTICE,
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
    preview = preview_processing_config(inputs)
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
        "execution_enabled": EXECUTION_ENABLED,
        "safety_notice": SAFETY_NOTICE,
        "missing": [field.model_dump() for field in preview.missing],
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
        safety_notice=SAFETY_NOTICE,
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

    return ProcessingTaskResponse(
        task_id=metadata["task_id"],
        status=metadata["status"],
        task_dir=str(task_dir),
        config_path=str(config_path),
        metadata_path=str(metadata_path),
        missing=missing,
        config_yaml=config_path.read_text(encoding="utf-8"),
        safety_notice=metadata.get("safety_notice", SAFETY_NOTICE),
    )
