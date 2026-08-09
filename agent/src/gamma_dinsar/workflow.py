from __future__ import annotations

from pathlib import Path

from gamma_dinsar.config import TaskConfig
from gamma_dinsar.executor import GammaAction, GammaExecutor, GammaExecutionError, MissingOutputError
from gamma_dinsar.stages import STAGES, STAGE_NAMES, stage_index
from gamma_dinsar.state import StageStatus, StateStore, TaskState


def task_dir(config: TaskConfig) -> Path:
    return config.output_dir / config.task_id


def run_workflow(
    config: TaskConfig,
    executor: GammaExecutor,
    *,
    from_stage: str | None = None,
) -> TaskState:
    start_index = stage_index(from_stage) if from_stage else 0
    store = StateStore(config.output_dir, config.task_id)
    state = store.load_or_create() if config.resume or from_stage else TaskState.new(config.task_id)
    store.save(state)

    base_dir = task_dir(config)
    logs_dir = base_dir / "logs"

    for name in STAGE_NAMES[:start_index]:
        if state.stages[name].status == StageStatus.PENDING:
            store.mark(state, name, StageStatus.SKIPPED, message=f"skipped before resume stage {from_stage}")

    for stage in STAGES[start_index:]:
        if config.resume and state.stages[stage.name].status == StageStatus.SUCCESS:
            continue

        log_file = logs_dir / f"{stage.name}.log"
        store.mark(
            state,
            stage.name,
            StageStatus.RUNNING,
            message="stage started",
            log_file=str(log_file),
        )

        action = GammaAction(
            stage_name=stage.name,
            description=f"placeholder action for {stage.name}; no real GAMMA command is defined",
            expected_outputs=tuple(stage.output_paths(base_dir)),
        )

        try:
            executor.run_action(action, log_file)
            _assert_outputs_exist(action.expected_outputs)
        except GammaExecutionError as exc:
            store.mark(state, stage.name, StageStatus.FAILED, message=str(exc), log_file=str(log_file))
            break
        except Exception as exc:
            store.mark(state, stage.name, StageStatus.FAILED, message=f"unexpected error: {exc}", log_file=str(log_file))
            break
        else:
            store.mark(state, stage.name, StageStatus.SUCCESS, message="stage completed", log_file=str(log_file))

    return state


def _assert_outputs_exist(outputs: tuple[Path, ...]) -> None:
    missing = [str(path) for path in outputs if not path.exists()]
    if missing:
        raise MissingOutputError("expected output files are missing: " + ", ".join(missing))
