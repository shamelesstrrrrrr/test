from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


QueryType = Literal["concept", "workflow", "command", "parameter", "file_layout", "code_template"]
VerificationStatus = Literal[
    "manual_verified",
    "partial_manual_evidence",
    "code_reference",
    "web_reference",
    "insufficient_evidence",
]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = Field(default=None, alias="sessionId")
    messages: list[ChatTurn] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class Citation(BaseModel):
    id: str
    source: str
    page: str
    command_name: str
    section: str
    verification_status: VerificationStatus
    retrieval_score: float
    excerpt: str


class ChatResponse(BaseModel):
    content: str
    queryTypes: list[QueryType]
    citations: list[Citation]
    mode: Literal["rag_api"] = "rag_api"


class HealthResponse(BaseModel):
    status: Literal["ok", "missing_config"]
    embedding_model: str
    chat_model: str
    index_loaded: bool
    code_index_loaded: bool = False
    web_search_enabled: bool = False
    web_search_provider: str = "disabled"
    missing: list[str]


class ProcessingDefaultParameter(BaseModel):
    key: str
    default_value: Any
    description: str
    options: list[str] = Field(default_factory=list)


class ProcessingDefaultGroup(BaseModel):
    name: str
    parameters: list[ProcessingDefaultParameter]


class ProcessingFieldInfo(BaseModel):
    key: str
    description: str
    default_value: Any = None
    options: list[str] = Field(default_factory=list)


class ProcessingStepInfo(BaseModel):
    key: str
    title: str
    description: str
    required_inputs: list[str] = Field(default_factory=list)
    default_inputs: list[str] = Field(default_factory=list)


class ProcessingWorkflowPreset(BaseModel):
    key: str
    title: str
    start_step: str
    end_step: str
    description: str


class ProcessingSensorProfile(BaseModel):
    key: str
    title: str
    short_title: str
    raw_input_key: str
    raw_input_label: str
    raw_input_description: str
    workflow_steps: list[str]
    preprocessing_wrapper: str | None = None
    preprocessing_commands: list[str] = Field(default_factory=list)
    source_scripts: list[str] = Field(default_factory=list)
    polarization_options: list[str] = Field(default_factory=list)
    needs_orbit_dir: bool = False
    coregistration_options: list[str] = Field(default_factory=list)
    default_coregistration_method: str | None = None
    note: str = ""


class ProcessingDefaultsResponse(BaseModel):
    execution_enabled: bool = False
    safety_notice: str
    required_inputs: list[ProcessingFieldInfo]
    crop_inputs: list[ProcessingFieldInfo]
    visible_optional_inputs: list[ProcessingFieldInfo]
    default_groups: list[ProcessingDefaultGroup]
    processing_steps: list[ProcessingStepInfo]
    workflow_presets: list[ProcessingWorkflowPreset]
    sensor_profiles: list[ProcessingSensorProfile]
    minimal_template: dict[str, Any]
    minimal_template_yaml: str


class ProcessingConfigRequest(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)


class ProcessingMissingField(BaseModel):
    key: str
    description: str


class ProcessingConfigPreviewResponse(BaseModel):
    status: Literal["ready", "needs_input"]
    missing: list[ProcessingMissingField]
    config: dict[str, Any]
    effective_parameters: dict[str, Any]
    config_yaml: str
    workflow: str
    workflow_start: str
    workflow_end: str
    selected_steps: list[ProcessingStepInfo]
    required_field_keys: list[str]
    execution_enabled: bool = False
    safety_notice: str


class ProcessingTaskCreateRequest(ProcessingConfigRequest):
    allow_incomplete: bool = False


class ProcessingTaskResponse(BaseModel):
    task_id: str
    status: Literal["pending_review", "ready_for_linux_worker"]
    task_dir: str
    config_path: str
    metadata_path: str
    missing: list[ProcessingMissingField]
    config_yaml: str
    workflow: str
    workflow_start: str
    workflow_end: str
    selected_steps: list[ProcessingStepInfo]
    required_field_keys: list[str]
    execution_enabled: bool = False
    safety_notice: str


ProcessingJobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancel_requested",
    "cancelled",
]


class ProcessingNotificationRequest(BaseModel):
    enabled: bool = False
    qq_mail_user: str | None = None
    qq_mail_auth_code: str | None = None
    qq_mail_to: str | None = None


class ProcessingJobCreateRequest(BaseModel):
    task_id: str
    workflow: str = "configured"
    notification: ProcessingNotificationRequest | None = None


class ProcessingJobStep(BaseModel):
    key: str
    title: str
    status: Literal["pending", "running", "succeeded", "failed", "skipped"] = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    message: str | None = None


class ProcessingJobResponse(BaseModel):
    job_id: str
    task_id: str
    status: ProcessingJobStatus
    workflow: str
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: int = 0
    current_step: str | None = None
    steps: list[ProcessingJobStep] = Field(default_factory=list)
    config_path: str
    job_path: str
    log_path: str
    pid: int | None = None
    return_code: int | None = None
    error: str | None = None
    log_tail: str = ""
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    execution_enabled: bool = False
    safety_notice: str
    auto_archive_path: str | None = None
    auto_archived_items: list[str] = Field(default_factory=list)
    notification_status: str | None = None


class ProcessingFileBrowserRoot(BaseModel):
    name: str
    path: str


class ProcessingFileBrowserEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: int | None = None
    modified_at: str | None = None


class ProcessingFileBrowserResponse(BaseModel):
    current_path: str
    parent_path: str | None = None
    roots: list[ProcessingFileBrowserRoot]
    entries: list[ProcessingFileBrowserEntry]
