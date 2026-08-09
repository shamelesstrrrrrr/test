from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = PROJECT_ROOT / "agent"
SAR_AGENT_DIR = AGENT_ROOT / "src" / "gamma_dinsar" / "sar_agent"

for import_path in (AGENT_ROOT, SAR_AGENT_DIR):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))


WORKFLOW_STEPS: tuple[tuple[str, str, str], ...] = (
    ("unzip_s1", "解压 Sentinel-1 ZIP", "run_unzip_s1_real"),
    ("generate_slc", "生成 SLC", "run_generate_slc_real"),
    ("extract_burst", "提取 Burst", "run_extract_burst_real"),
    ("slc_geo", "主影像地理编码", "run_slc_geo_real"),
    ("coregistration", "主从影像配准", "run_slc_coreg_multi_real"),
    ("crop_rslc", "RSLC 裁剪", "run_slc_copy_crop_all_real"),
    ("write_rslc_tab", "生成 RSLC_tab", "write_rslc_tab_from_list_real"),
    ("base_calc", "生成基线和 itab", "run_base_calc_itab_real"),
    ("mk_mli_all", "生成 RMLI 强度图", "run_mk_mli_all_real"),
    ("diff_workflow", "生成差分干涉图", "run_diff_workflow_real"),
    ("select_shp", "SHP 同质像元选取", "run_select_shp_matlab_real"),
    ("phase_optimization", "相位优化", "run_phase_optimization_workflow_real"),
    ("file_construct", "组织 StaMPS 时序文件", "run_file_construct_real"),
    ("point_selection", "候选点选取", "run_point_selection_real"),
    ("stamps_processing", "StaMPS 处理", "run_stamps_processing_real"),
)

WORKFLOWS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "full": WORKFLOW_STEPS,
}

FAILED_KEYWORDS = (
    "失败",
    "错误",
    "缺少参数",
    "不存在",
    "Traceback",
    "ERROR",
    "Error",
    "error",
    "returncode=",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_job(job_path: Path) -> dict[str, Any]:
    return json.loads(job_path.read_text(encoding="utf-8"))


def save_job(job_path: Path, job: dict[str, Any]) -> None:
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")


def append_log(log_path: Path, text: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text.rstrip())
        handle.write("\n")


def progress_percent(job: dict[str, Any]) -> int:
    total = int(job.get("progress_total") or 0)
    current = int(job.get("progress_current") or 0)
    if total <= 0:
        return 0
    return round((current / total) * 100)


def update_step(
    job_path: Path,
    step_key: str,
    *,
    status: str,
    message: str | None = None,
    current_step: str | None = None,
) -> dict[str, Any]:
    job = load_job(job_path)
    for step in job.get("steps", []):
        if step.get("key") != step_key:
            continue
        step["status"] = status
        if status == "running":
            step["started_at"] = step.get("started_at") or utc_now()
        if status in {"succeeded", "failed", "skipped"}:
            step["finished_at"] = utc_now()
        if message:
            step["message"] = message[:1000]
        break

    job["current_step"] = current_step
    job["progress_current"] = sum(1 for step in job.get("steps", []) if step.get("status") == "succeeded")
    job["progress_percent"] = progress_percent(job)
    save_job(job_path, job)
    return job


def is_failure_output(output: str) -> bool:
    return any(keyword in output for keyword in FAILED_KEYWORDS)


def run_job(job_path: Path, config_path: Path, log_path: Path, workflow: str) -> int:
    steps = WORKFLOWS.get(workflow)
    if not steps:
        raise ValueError(f"unsupported workflow: {workflow}")

    job = load_job(job_path)
    job["status"] = "running"
    job["started_at"] = utc_now()
    job["progress_total"] = len(steps)
    job["progress_current"] = 0
    job["progress_percent"] = 0
    job["steps"] = [
        {"key": key, "title": title, "status": "pending", "message": None}
        for key, title, _method_name in steps
    ]
    save_job(job_path, job)

    append_log(log_path, f"[{utc_now()}] job started: workflow={workflow}")
    append_log(log_path, f"[{utc_now()}] config={config_path}")

    from tools import AgentTools  # type: ignore

    agent_tools = AgentTools()
    load_result = agent_tools.load_task_config(str(config_path))
    append_log(log_path, "## load_task_config")
    append_log(log_path, load_result)

    if is_failure_output(load_result):
        job = load_job(job_path)
        job["status"] = "failed"
        job["return_code"] = 1
        job["error"] = load_result[-2000:]
        job["finished_at"] = utc_now()
        save_job(job_path, job)
        append_log(log_path, f"[{utc_now()}] job failed while loading config")
        return 1

    for step_key, title, method_name in steps:
        update_step(job_path, step_key, status="running", current_step=step_key)
        append_log(log_path, f"\n## {title} ({step_key})")

        method = getattr(agent_tools, method_name)
        try:
            output = str(method())
        except Exception:
            output = traceback.format_exc()

        append_log(log_path, output)

        if is_failure_output(output):
            update_step(job_path, step_key, status="failed", message=output[-1000:], current_step=step_key)
            job = load_job(job_path)
            job["status"] = "failed"
            job["return_code"] = 1
            job["error"] = output[-2000:]
            job["finished_at"] = utc_now()
            job["progress_percent"] = progress_percent(job)
            save_job(job_path, job)
            append_log(log_path, f"[{utc_now()}] job failed at {step_key}")
            return 1

        update_step(job_path, step_key, status="succeeded", message=output[-1000:], current_step=step_key)

    job = load_job(job_path)
    job["status"] = "succeeded"
    job["return_code"] = 0
    job["finished_at"] = utc_now()
    job["current_step"] = None
    job["progress_current"] = len(steps)
    job["progress_percent"] = 100
    save_job(job_path, job)
    append_log(log_path, f"[{utc_now()}] job succeeded")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a saved gamma_dinsar processing job.")
    parser.add_argument("--job-path", type=Path, required=True)
    parser.add_argument("--config-path", type=Path, required=True)
    parser.add_argument("--log-path", type=Path, required=True)
    parser.add_argument("--workflow", default="full")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return run_job(args.job_path, args.config_path, args.log_path, args.workflow)
    except Exception:
        trace = traceback.format_exc()
        append_log(args.log_path, trace)
        if args.job_path.exists():
            job = load_job(args.job_path)
            job["status"] = "failed"
            job["return_code"] = 1
            job["error"] = trace[-2000:]
            job["finished_at"] = utc_now()
            save_job(args.job_path, job)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
