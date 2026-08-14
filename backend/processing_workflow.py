from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any


AGENT_DEFAULTS_DIR = Path(__file__).resolve().parents[1] / "agent" / "src" / "gamma_dinsar" / "sar_agent"
if str(AGENT_DEFAULTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DEFAULTS_DIR))

from sensor_profiles import get_sensor_profile


@dataclass(frozen=True)
class ProcessingStepSpec:
    key: str
    title: str
    method_name: str
    description: str
    required_inputs: tuple[str, ...] = ()
    default_inputs: tuple[str, ...] = ()


PROCESSING_STEPS: tuple[ProcessingStepSpec, ...] = (
    ProcessingStepSpec(
        "prepare_sensor_raw",
        "准备非 Sentinel 原始数据",
        "run_prepare_sensor_raw_real",
        "复制已解压原始数据到任务目录，后续封装脚本只操作任务副本。",
        ("task_root", "raw_data_dir"),
    ),
    ProcessingStepSpec(
        "unzip_s1",
        "解压 Sentinel-1 ZIP",
        "run_unzip_s1_real",
        "从原始 ZIP 数据解压到任务目录的 SLC 子目录，并在其中生成按日期组织的 SLC。",
        ("task_root", "raw_zip_dir"),
    ),
    ProcessingStepSpec(
        "generate_slc",
        "生成 SLC",
        "run_generate_slc_real",
        "基于已解压数据生成 SLC 数据。",
        ("task_root", "env_scripts", "satellite", "polarization", "swath"),
    ),
    ProcessingStepSpec(
        "apply_orbit",
        "应用精密轨道",
        "run_apply_orbit_real",
        "为 ENVISAT 或 ERS SLC 应用封装脚本支持的精密轨道校正。",
        ("task_root", "env_scripts", "orbit_dir"),
    ),
    ProcessingStepSpec(
        "extract_burst",
        "提取 Burst",
        "run_extract_burst_real",
        "从 SLC 中提取指定 burst 范围。",
        ("task_root", "env_scripts", "polarization", "swath", "bn_start1", "bn_end1"),
        ("bn_start2", "bn_end2", "bn_start3", "bn_end3"),
    ),
    ProcessingStepSpec(
        "slc_geo",
        "主影像地理编码",
        "run_slc_geo_real",
        "为主影像生成地理编码相关结果。",
        ("task_root", "env_scripts", "dem_file", "master_date"),
        ("range_looks", "azimuth_looks", "lat_ovr", "lon_ovr"),
    ),
    ProcessingStepSpec(
        "coregistration",
        "主从影像配准",
        "run_slc_coreg_multi_real",
        "使用地理编码结果对影像序列进行配准。",
        ("task_root", "env_scripts", "polarization", "swath"),
    ),
    ProcessingStepSpec(
        "crop_rslc",
        "RSLC 裁剪",
        "run_slc_copy_crop_all_real",
        "按人工确认的范围裁剪 RSLC。",
        ("task_root", "env_scripts", "master_date", "polarization", "swath"),
        ("data_format", "scale_factor"),
    ),
    ProcessingStepSpec(
        "stage_rslc",
        "整理 RSLC 结果",
        "run_stage_rslc_real",
        "将非 Sentinel 卫星的配准结果整理到统一的 SLC_copy 目录结构，供后续 InSAR 步骤使用。",
        ("task_root", "master_date"),
    ),
    ProcessingStepSpec(
        "write_rslc_tab",
        "生成 RSLC_tab",
        "write_rslc_tab_from_list_real",
        "从影像列表生成后续步骤需要的 RSLC_tab。",
        ("task_root",),
        ("rslc_template", "rslc_par_template"),
    ),
    ProcessingStepSpec(
        "base_calc",
        "生成基线和 itab",
        "run_base_calc_itab_real",
        "生成 SBAS 基线文件和 itab 文件。",
        ("task_root", "env_scripts", "master_date"),
        ("itab_type", "base_calc_plot_flag", "bperp_min", "bperp_max", "delta_t_min", "delta_t_max", "delta_n_max"),
    ),
    ProcessingStepSpec(
        "mk_mli_all",
        "生成 RMLI 强度图",
        "run_mk_mli_all_real",
        "根据 RSLC_tab 生成多视强度图。",
        ("task_root", "env_scripts"),
        ("rlks", "azlks"),
    ),
    ProcessingStepSpec(
        "diff_workflow",
        "生成差分干涉图",
        "run_diff_workflow_real",
        "按选择的差分方法生成差分干涉图。",
        ("task_root", "env_scripts", "dem_file", "master_date", "diff_method"),
        ("rlks", "azlks", "diff_param_1", "diff_s_value", "diff_e_value"),
    ),
    ProcessingStepSpec(
        "select_shp",
        "SHP 同质像元选取",
        "run_select_shp_matlab_real",
        "调用 MATLAB 方法选择同质像元。",
        ("task_root", "env_scripts", "master_date", "matlab_func_dir", "shp_method"),
        ("cal_win_range", "cal_win_azimuth", "alpha", "matlab_command"),
    ),
    ProcessingStepSpec(
        "phase_optimization",
        "相位优化",
        "run_phase_optimization_workflow_real",
        "调用相位优化方法生成优化结果。",
        ("task_root", "env_scripts", "matlab_func_dir", "phase_opt_method", "shp_method"),
        ("fit_threshold", "ref_id", "block_size", "phase_opt_output_name", "matlab_command"),
    ),
    ProcessingStepSpec(
        "file_construct",
        "组织 StaMPS 时序文件",
        "run_file_construct_real",
        "把差分、RMLI、基线等结果整理为 StaMPS 时序输入。",
        ("task_root", "env_scripts", "master_date"),
        ("ts_flag",),
    ),
    ProcessingStepSpec(
        "point_selection",
        "候选点选取",
        "run_point_selection_real",
        "按 mt_prep_gamma、DSC 或 PDS 路线选取候选点。",
        ("task_root", "env_scripts", "master_date", "point_selection_method"),
        ("psc_da_thresh", "rg_patches", "az_patches", "rg_overlap", "az_overlap", "fit_threshold", "phase_opt_output_name", "matlab_command", "mt_prep_gamma_addds_command"),
    ),
    ProcessingStepSpec(
        "stamps_processing",
        "StaMPS 处理",
        "run_stamps_processing_real",
        "进入 StaMPS 工作目录执行时序处理。",
        ("task_root", "env_scripts", "stamps_mode"),
        ("matlab_command",),
    ),
)

STEP_BY_KEY = {step.key: step for step in PROCESSING_STEPS}


def steps_for_sensor(sensor_profile: Any = None) -> tuple[ProcessingStepSpec, ...]:
    profile = get_sensor_profile(sensor_profile)
    return tuple(STEP_BY_KEY[key] for key in profile.workflow_steps)


def _step_index_for_sensor(sensor_profile: Any = None) -> dict[str, int]:
    return {step.key: index for index, step in enumerate(steps_for_sensor(sensor_profile))}

WORKFLOW_PRESETS: tuple[dict[str, str], ...] = (
    {
        "key": "full",
        "title": "完整 DInSAR 流程",
        "start_step": "unzip_s1",
        "end_step": "stamps_processing",
        "description": "从 ZIP 解压一直运行到 StaMPS 处理。",
    },
    {
        "key": "prepare_until_burst",
        "title": "只做到 Burst 提取",
        "start_step": "unzip_s1",
        "end_step": "extract_burst",
        "description": "适合先准备 SLC_select，再人工检查 burst 或裁剪范围。",
    },
    {
        "key": "coreg_until_crop",
        "title": "配准到裁剪",
        "start_step": "slc_geo",
        "end_step": "crop_rslc",
        "description": "已有 SLC_select 时，从主影像地理编码运行到 RSLC 裁剪。",
    },
    {
        "key": "diff_only",
        "title": "只生成差分干涉图",
        "start_step": "diff_workflow",
        "end_step": "diff_workflow",
        "description": "已有 RSLC_tab、itab、RMLI 等中间结果时，仅重跑差分干涉。",
    },
    {
        "key": "time_series_only",
        "title": "只做时序后处理",
        "start_step": "select_shp",
        "end_step": "stamps_processing",
        "description": "已有差分干涉结果时，从 SHP/相位优化运行到 StaMPS。",
    },
)

PRESET_BY_KEY = {preset["key"]: preset for preset in WORKFLOW_PRESETS}


def _workflow_presets_for_sensor(sensor_profile: Any = None) -> tuple[dict[str, str], ...]:
    profile = get_sensor_profile(sensor_profile)
    if profile.key == "sentinel_1":
        return WORKFLOW_PRESETS

    steps = steps_for_sensor(profile.key)
    step_keys = {step.key for step in steps}
    presets: list[dict[str, str]] = [
        {
            "key": "full",
            "title": "完整 InSAR / 时序流程",
            "start_step": steps[0].key,
            "end_step": steps[-1].key,
            "description": "从已解压原始数据副本开始，依次完成 SLC、配准、差分干涉和后续时序处理。",
        },
        {
            "key": "prepare_until_rslc",
            "title": "准备到 RSLC",
            "start_step": steps[0].key,
            "end_step": "stage_rslc",
            "description": "完成原始数据准备、SLC 生成、必要的精轨校正、配准与 RSLC 整理。",
        },
        {
            "key": "diff_only",
            "title": "只生成差分干涉图",
            "start_step": "diff_workflow",
            "end_step": "diff_workflow",
            "description": "已有 RSLC_tab、itab 和 RMLI 等中间结果时，只重跑差分干涉。",
        },
        {
            "key": "time_series_only",
            "title": "只做时序后处理",
            "start_step": "select_shp",
            "end_step": "stamps_processing",
            "description": "已有差分干涉结果时，从 SHP/相位优化继续到 StaMPS。",
        },
    ]
    return tuple(
        preset
        for preset in presets
        if preset["start_step"] in step_keys and preset["end_step"] in step_keys
    )


def _has_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def default_start_step(sensor_profile: Any = None) -> str:
    return steps_for_sensor(sensor_profile)[0].key


def default_end_step(sensor_profile: Any = None) -> str:
    return steps_for_sensor(sensor_profile)[-1].key


def normalize_step_range(
    start_step: Any = None,
    end_step: Any = None,
    sensor_profile: Any = None,
) -> tuple[str, str]:
    steps = steps_for_sensor(sensor_profile)
    step_index = _step_index_for_sensor(sensor_profile)
    start = str(start_step or default_start_step(sensor_profile)).strip()
    end = str(end_step or default_end_step(sensor_profile)).strip()

    if start not in step_index:
        raise ValueError(f"不支持的起始步骤：{start}")
    if end not in step_index:
        raise ValueError(f"不支持的结束步骤：{end}")
    if step_index[start] > step_index[end]:
        raise ValueError("起始步骤不能晚于结束步骤")

    return start, end


def workflow_from_inputs(inputs: dict[str, Any]) -> str:
    sensor_profile = inputs.get("sensor_profile")
    step_index = _step_index_for_sensor(sensor_profile)
    presets = {preset["key"]: preset for preset in _workflow_presets_for_sensor(sensor_profile)}
    preset = str(inputs.get("workflow_preset") or "").strip()
    if preset and preset in presets:
        selected = presets[preset]
        return f"range:{selected['start_step']}:{selected['end_step']}"

    requested_start = inputs.get("workflow_start")
    requested_end = inputs.get("workflow_end")
    if requested_start not in step_index:
        requested_start = default_start_step(sensor_profile)
    if requested_end not in step_index:
        requested_end = default_end_step(sensor_profile)
    start, end = normalize_step_range(
        requested_start,
        requested_end,
        sensor_profile,
    )
    return f"range:{start}:{end}"


def workflow_to_range(workflow: str, sensor_profile: Any = None) -> tuple[str, str]:
    presets = {preset["key"]: preset for preset in _workflow_presets_for_sensor(sensor_profile)}
    step_index = _step_index_for_sensor(sensor_profile)
    value = (workflow or "full").strip()

    if value == "configured":
        raise ValueError("configured workflow must be resolved before worker execution")

    if value in presets:
        selected = presets[value]
        return normalize_step_range(selected["start_step"], selected["end_step"], sensor_profile)

    if value == "full":
        return normalize_step_range(default_start_step(sensor_profile), default_end_step(sensor_profile), sensor_profile)

    if value in step_index:
        return normalize_step_range(value, value, sensor_profile)

    if value.startswith("range:"):
        parts = value.split(":")
        if len(parts) != 3:
            raise ValueError(f"处理范围格式无效：{workflow}")
        return normalize_step_range(parts[1], parts[2], sensor_profile)

    raise ValueError(f"不支持的处理范围：{workflow}")


def resolve_workflow_steps(workflow: str, sensor_profile: Any = None) -> tuple[ProcessingStepSpec, ...]:
    start, end = workflow_to_range(workflow, sensor_profile)
    steps = steps_for_sensor(sensor_profile)
    step_index = _step_index_for_sensor(sensor_profile)
    return steps[step_index[start] : step_index[end] + 1]


def required_field_keys_for_steps(
    steps: tuple[ProcessingStepSpec, ...],
    inputs: dict[str, Any],
) -> list[str]:
    keys: list[str] = []
    profile = get_sensor_profile(inputs.get("sensor_profile"))

    def add(field_key: str) -> None:
        if field_key not in keys:
            keys.append(field_key)

    for step in steps:
        if profile.key != "sentinel_1" and step.key == "generate_slc":
            add("task_root")
            add("env_scripts")
            if profile.polarization_options:
                add("polarization")
            continue

        if profile.key != "sentinel_1" and step.key == "coregistration":
            add("task_root")
            add("env_scripts")
            needs_reference_image = profile.key in {"terrasar_x", "gf3"} or (
                profile.key == "ers_ims"
                and str(inputs.get("coregistration_method") or profile.default_coregistration_method) == "cross_correlation"
            )
            if needs_reference_image:
                add("master_date")
            if len(profile.coregistration_options) > 1:
                add("coregistration_method")
            continue

        for key in step.required_inputs:
            add(key)

        if step.key == "crop_rslc":
            for key in ("crop_roff", "crop_nr", "crop_loff", "crop_nl"):
                add(key)

        if step.key == "point_selection":
            method = str(inputs.get("point_selection_method") or "dsc_pds").strip().lower()
            if method in {"dsc_select", "dsc", "dsc_pds", "pds", "ds"}:
                add("matlab_func_dir")

    return keys


def default_field_keys_for_steps(
    steps: tuple[ProcessingStepSpec, ...],
    inputs: dict[str, Any],
) -> list[str]:
    keys: list[str] = []
    profile = get_sensor_profile(inputs.get("sensor_profile"))

    def add(field_key: str) -> None:
        if field_key not in keys:
            keys.append(field_key)

    for step in steps:
        for key in step.default_inputs:
            add(key)

        if profile.key != "sentinel_1" and step.key == "coregistration":
            add("coregistration_method")

        if step.key == "diff_workflow":
            method = str(inputs.get("diff_method") or "initial").strip().lower()
            if method == "unwrapped_ls":
                for key in ("adf_alpha", "adf_window", "unw_alpha"):
                    add(key)

        if step.key == "point_selection":
            method = str(inputs.get("point_selection_method") or "dsc_pds").strip().lower()
            if method in {"dsc_select", "dsc", "dsc_pds", "pds", "ds"}:
                add("matlab_func_dir")

    return keys


def missing_fields_for_workflow(inputs: dict[str, Any], workflow: str) -> list[str]:
    steps = resolve_workflow_steps(workflow, inputs.get("sensor_profile"))
    required_keys = required_field_keys_for_steps(steps, inputs)
    return [key for key in required_keys if not _has_value(inputs.get(key))]


def workflow_step_payloads(sensor_profile: Any = None) -> list[dict[str, Any]]:
    return [
        {
            "key": step.key,
            "title": step.title,
            "description": step.description,
            "required_inputs": list(step.required_inputs),
            "default_inputs": list(step.default_inputs),
        }
        for step in steps_for_sensor(sensor_profile)
    ]


def all_workflow_step_payloads() -> list[dict[str, Any]]:
    return [
        {
            "key": step.key,
            "title": step.title,
            "description": step.description,
            "required_inputs": list(step.required_inputs),
            "default_inputs": list(step.default_inputs),
        }
        for step in PROCESSING_STEPS
    ]


def workflow_preset_payloads(sensor_profile: Any = None) -> list[dict[str, str]]:
    return [dict(preset) for preset in _workflow_presets_for_sensor(sensor_profile)]
