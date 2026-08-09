from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gamma_dinsar.config import MockConfig, MockScenario


class GammaExecutionError(RuntimeError):
    pass


class GammaTimeoutError(GammaExecutionError):
    pass


class MissingOutputError(GammaExecutionError):
    pass


@dataclass(frozen=True)
class GammaAction:
    stage_name: str
    description: str
    expected_outputs: tuple[Path, ...]


@dataclass(frozen=True)
class GammaResult:
    stage_name: str
    return_code: int
    stdout: str
    stderr: str


class GammaExecutor(Protocol):
    def run_action(self, action: GammaAction, log_file: Path) -> GammaResult:
        """Run a validated GAMMA action.

        Implementations must not accept free-form LLM-generated shell commands.
        Real implementations should execute only user-confirmed command templates.
        """


class MockGammaExecutor:
    def __init__(self, config: MockConfig) -> None:
        self.config = config

    def run_action(self, action: GammaAction, log_file: Path) -> GammaResult:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        scenario = self.config.scenario
        fails_here = self.config.fail_stage in {None, action.stage_name}

        if scenario == MockScenario.COMMAND_FAILURE and fails_here:
            self._write_log(log_file, action, "mock command failure")
            raise GammaExecutionError(f"mock command failure at stage {action.stage_name}")

        if scenario == MockScenario.TIMEOUT and fails_here:
            self._write_log(log_file, action, "mock timeout")
            raise GammaTimeoutError(f"mock timeout at stage {action.stage_name}")

        if scenario == MockScenario.MISSING_OUTPUT and fails_here:
            self._write_log(log_file, action, "mock missing output")
            raise MissingOutputError(f"mock output missing at stage {action.stage_name}")

        for output in action.expected_outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                f"Mock product for {action.stage_name}. This is not a real GAMMA D-InSAR output.\n",
                encoding="utf-8",
            )

        self._write_log(log_file, action, "mock success")
        return GammaResult(
            stage_name=action.stage_name,
            return_code=0,
            stdout=f"mock success: {action.description}",
            stderr="",
        )

    @staticmethod
    def _write_log(log_file: Path, action: GammaAction, message: str) -> None:
        log_file.write_text(
            "\n".join(
                [
                    f"stage={action.stage_name}",
                    f"description={action.description}",
                    f"message={message}",
                    "note=mock execution only; no real GAMMA command was run",
                    "",
                ]
            ),
            encoding="utf-8",
        )
