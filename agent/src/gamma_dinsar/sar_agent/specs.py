from dataclasses import dataclass, field
from typing import Any, Literal

VerificationStatus = Literal[
    "verified_from_document",
    "needs_verified_prompt_order",
    "needs_user_confirmed_template",
    "needs_runtime_verification",
]

CommandMode = Literal["interactive", "argv", "manual"]


@dataclass(frozen=True)
class CommandInputSpec:
    input_key: str
    label: str
    required: bool = True
    default: Any | None = None
    note: str | None = None


@dataclass(frozen=True)
class CommandSpec:
    command_id: str
    command_name: str
    mode: CommandMode
    verification_status: VerificationStatus
    stdin_sequence: list[CommandInputSpec] = field(default_factory=list)
    argv_sequence: list[CommandInputSpec] = field(default_factory=list)
    argv_template: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass(frozen=True)
class StageSpec:
    name: str
    title: str
    description: str
    required_inputs: list[str] = field(default_factory=list)
    optional_inputs: dict[str, Any] = field(default_factory=dict)
    derived_inputs: dict[str, str] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    command_template_id: str | None = None