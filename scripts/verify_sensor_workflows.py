"""Static preflight for the multi-sensor GAMMA processing integration.

This script does not invoke GAMMA, Bash, or any processing command. It checks
that the sensor profiles agree with local wrapper scripts and Python worker
entry points. A pass proves internal wiring only, not real GAMMA execution.
"""

from __future__ import annotations

import sys
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = PROJECT_ROOT / "agent" / "src" / "gamma_dinsar" / "sar_agent"
SOURCE_ROOT = PROJECT_ROOT / "\u5904\u7406\u4ee3\u7801" / "version2.0.2"

if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from sensor_profiles import SENSOR_PROFILES  # noqa: E402


VERBOSE = "--verbose" in sys.argv


WORKER_METHOD_BY_STEP = {
    "prepare_sensor_raw": "run_prepare_sensor_raw_real",
    "unzip_s1": "run_unzip_s1_real",
    "generate_slc": "run_generate_slc_real",
    "extract_burst": "run_extract_burst_real",
    "apply_orbit": "run_apply_orbit_real",
    "slc_geo": "run_slc_geo_real",
    "coregistration": "run_slc_coreg_multi_real",
    "crop_rslc": "run_slc_copy_crop_all_real",
    "stage_rslc": "run_stage_rslc_real",
    "write_rslc_tab": "write_rslc_tab_from_list_real",
    "base_calc": "run_base_calc_itab_real",
    "mk_mli_all": "run_mk_mli_all_real",
    "diff_workflow": "run_diff_workflow_real",
    "select_shp": "run_select_shp_matlab_real",
    "phase_optimization": "run_phase_optimization_workflow_real",
    "file_construct": "run_file_construct_real",
    "point_selection": "run_point_selection_real",
    "stamps_processing": "run_stamps_processing_real",
}


# These values come from the shell wrappers' parameter guards. They let the
# Windows-only preflight check our adapter call shape without invoking Bash or
# GAMMA.
SOURCE_ARGUMENT_CONTRACTS = (
    ("alos_palsar", "Preprocessing/ALOS/ALOS_SLC_Normal", "lt", 2),
    ("alos_palsar", "Preprocessing/ALOS/ALOS_SLC_GEO", "ne", 7),
    ("alos_palsar", "Preprocessing/ALOS/ALOS_SLC_COREG", "lt", 4),
    ("alos_palsar", "Preprocessing/ALOS/ALOS_SLC_COREG_DEM", "lt", 4),
    ("terrasar_x", "Preprocessing/TX/TX_SLC_Normal", "lt", 2),
    ("terrasar_x", "Preprocessing/TX/TX_SLC_GEO", "ne", 5),
    ("terrasar_x", "Preprocessing/TX/TX_SLC_COREG", "lt", 4),
    ("gf3", "Preprocessing/GF3/GF3_SLC", "ne", 1),
    ("gf3", "Preprocessing/GF3/GF3_GEO", "ne", 7),
    ("gf3", "Preprocessing/GF3/GF3_COREG", "lt", 4),
    ("radarsat_2", "Preprocessing/Radasat/RADA2_SLC_Normal", "lt", 2),
    ("radarsat_2", "Preprocessing/Radasat/RADA2_SLC_GEO", "ne", 5),
    ("radarsat_2", "Preprocessing/Radasat/RADA2_SLC_COREG", "lt", 5),
    ("envisat_asar", "Preprocessing/ENVISAT/ENVISAT_mkdir", "ne", 1),
    ("envisat_asar", "Preprocessing/ENVISAT/ENVISAT_SLC", "ne", 1),
    ("envisat_asar", "Preprocessing/ENVISAT/ENVISAT_OPOD", "ne", 2),
    ("envisat_asar", "Preprocessing/ENVISAT/ENVISAT_GEO", "ne", 7),
    ("envisat_asar", "Preprocessing/ENVISAT/ENVISAT_coreg", "ne", 4),
    ("ers_ims", "Preprocessing/ERS-IMS/ERS_mkdir", "ne", 1),
    ("ers_ims", "Preprocessing/ERS-IMS/ERS_SLC", "ne", 1),
    ("ers_ims", "Preprocessing/ERS-IMS/ERS_OPOD", "ne", 2),
    ("ers_ims", "Preprocessing/ERS-IMS/ERS_GEO", "ne", 7),
    ("ers_ims", "Preprocessing/ERS-IMS/ERS_COREG_CC", "ne", 4),
    ("ers_ims", "Preprocessing/ERS-IMS/ERS_COREG_DEM", "ne", 4),
)


# Exact non-Sentinel adapter ordering. Keeping this separate from the source
# wrapper evidence catches accidental argument swaps in the Python worker.
EXECUTOR_COMMAND_CONTRACTS = (
    '("ALOS_SLC_COREG", str(slc_path), str(list_path), str(coreg_path), str(geo_path))',
    '("ALOS_SLC_COREG_DEM", str(slc_path), str(geo_path), str(list_path), str(coreg_path))',
    '("TX_SLC_COREG", str(slc_path), str(list_path), str(ref), str(coreg_path))',
    '("GF3_COREG", str(slc_path), str(list_path), str(coreg_path), str(ref))',
    '("RADA2_SLC_COREG", str(slc_path), str(list_path), str(coreg_path), str(geo_path), code)',
    '("ENVISAT_coreg", str(coreg_path), str(geo_path), str(slc_path), str(list_path))',
    '("ERS_COREG_CC", str(slc_path), str(list_path), str(ref), str(coreg_path))',
    '("ERS_COREG_DEM", str(coreg_path), str(geo_path), str(slc_path), str(list_path))',
)


def cn(value: str) -> str:
    return value.encode("ascii").decode("unicode_escape")


FOUND_SCRIPT = cn("\\u627e\\u5230\\u5c01\\u88c5\\u811a\\u672c")
UNIQUE_PROFILE = cn("\\u536b\\u661f\\u6807\\u8bc6\\u552f\\u4e00")
DEFINED_WORKFLOW = cn("\\u5df2\\u5b9a\\u4e49\\u5904\\u7406\\u6d41\\u7a0b")
CONNECTED_TIMESERIES = cn("\\u6d41\\u7a0b\\u8fde\\u63a5\\u5230\\u65f6\\u5e8f\\u5904\\u7406")
FOUND_COMMAND = cn("\\u5728\\u5c01\\u88c5\\u6e90\\u7801\\u4e2d\\u627e\\u5230")
PREPARED_COPY = cn("\\u539f\\u59cb\\u6570\\u636e\\u5148\\u590d\\u5236\\u5230\\u4efb\\u52a1\\u526f\\u672c")
STAGED_RSLC = cn("\\u914d\\u51c6\\u7ed3\\u679c\\u4f1a\\u6574\\u7406\\u4e3a\\u7edf\\u4e00 RSLC \\u76ee\\u5f55")
NO_SENTINEL_BURST = cn("\\u672a\\u9519\\u8bef\\u52a0\\u5165 Sentinel Burst \\u6b65\\u9aa4")
STEP = cn("\\u6b65\\u9aa4")
CONNECTED_WORKER = cn("\\u5df2\\u8fde\\u63a5 worker \\u65b9\\u6cd5")
ARGUMENT_CONTRACT = cn("\\u53c2\\u6570\\u5951\\u7ea6")
COMMAND_ARGUMENT_ORDER = cn("\\u5c01\\u88c5\\u547d\\u4ee4\\u53c2\\u6570\\u987a\\u5e8f")


def check(condition: bool, message: str, failures: list[str]) -> None:
    if VERBOSE or not condition:
        print(("[PASS] " if condition else "[FAIL] ") + message)
    if not condition:
        failures.append(message)


def read_source_evidence(profile_key: str, source_scripts: tuple[str, ...], failures: list[str]) -> str:
    texts: list[str] = []
    for relative_path in source_scripts:
        path = SOURCE_ROOT / relative_path
        exists = path.is_file()
        check(exists, f"{profile_key}: {FOUND_SCRIPT} {relative_path}", failures)
        if exists:
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(texts)


def main() -> int:
    failures: list[str] = []
    tools_path = AGENT_DIR / "tools.py"
    tools_text = tools_path.read_text(encoding="utf-8", errors="replace") if tools_path.is_file() else ""
    executor_path = AGENT_DIR / "executor.py"
    executor_text = executor_path.read_text(encoding="utf-8", errors="replace") if executor_path.is_file() else ""
    check(bool(tools_text), cn("\\u8bfb\\u53d6 worker \\u5de5\\u5177\\u5b9e\\u73b0"), failures)
    check(bool(executor_text), cn("\\u8bfb\\u53d6\\u5c01\\u88c5\\u547d\\u4ee4\\u9002\\u914d\\u5b9e\\u73b0"), failures)

    seen_keys: set[str] = set()
    for profile in SENSOR_PROFILES:
        check(profile.key not in seen_keys, f"{profile.key}: {UNIQUE_PROFILE}", failures)
        seen_keys.add(profile.key)
        check(bool(profile.workflow_steps), f"{profile.key}: {DEFINED_WORKFLOW}", failures)
        check(
            profile.workflow_steps[-1] == "stamps_processing",
            f"{profile.key}: {CONNECTED_TIMESERIES}",
            failures,
        )

        evidence = read_source_evidence(profile.key, profile.source_scripts, failures)
        for command in profile.preprocessing_commands:
            check(command in evidence, f"{profile.key}: {FOUND_COMMAND} {command}", failures)

        if profile.key == "sentinel_1":
            check(
                "unzip_s1" in profile.workflow_steps and "extract_burst" in profile.workflow_steps,
                "sentinel_1: ZIP + Burst",
                failures,
            )
        else:
            check(
                profile.workflow_steps[0] == "prepare_sensor_raw",
                f"{profile.key}: {PREPARED_COPY}",
                failures,
            )
            check(
                "stage_rslc" in profile.workflow_steps,
                f"{profile.key}: {STAGED_RSLC}",
                failures,
            )
            check(
                "extract_burst" not in profile.workflow_steps,
                f"{profile.key}: {NO_SENTINEL_BURST}",
                failures,
            )

        for step in profile.workflow_steps:
            worker_method = WORKER_METHOD_BY_STEP.get(step)
            check(
                worker_method is not None and worker_method in tools_text,
                f"{profile.key}: {STEP} {step} {CONNECTED_WORKER}",
                failures,
            )

    for profile_key, relative_path, operator, argument_count in SOURCE_ARGUMENT_CONTRACTS:
        path = SOURCE_ROOT / relative_path
        content = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        pattern = rf"if\s+\[\s+\$#\s+-{operator}\s+{argument_count}\s+\]"
        check(
            bool(re.search(pattern, content)),
            f"{profile_key}: {relative_path} {ARGUMENT_CONTRACT} -{operator} {argument_count}",
            failures,
        )

    for command_contract in EXECUTOR_COMMAND_CONTRACTS:
        check(
            command_contract in executor_text,
            f"adapter: {COMMAND_ARGUMENT_ORDER} {command_contract}",
            failures,
        )

    print()
    if failures:
        print(f"STATIC_PREFLIGHT_FAILED: {len(failures)} check(s) failed. No GAMMA command was executed.")
        return 1

    print("STATIC_PREFLIGHT_OK: workflow, wrapper evidence, argument contracts, and worker wiring are consistent. No GAMMA command was executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
