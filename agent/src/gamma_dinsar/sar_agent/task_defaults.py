from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_PARAMETER_GROUPS: dict[str, dict[str, tuple[Any, str]]] = {
    "SLC 数据选择": {
        "satellite": ("S1A", "卫星类型；执行时会自动转换为 satellite_code，S1A=0，S1B=1。"),
        "polarization": ("VV", "极化方式；执行时会自动转换为 polarization_code，VV=0，VH=1。"),
        "swath": ("IW1", "子波束；执行时会自动转换为 swath_code，IW1=1，IW2=2，IW3=3。"),
    },
    "Burst 提取": {
        "bn_start2": ("", "第二组 burst 起始编号；留空表示不使用第二组。"),
        "bn_end2": ("", "第二组 burst 结束编号；留空表示不使用第二组。"),
        "bn_start3": ("", "第三组 burst 起始编号；留空表示不使用第三组。"),
        "bn_end3": ("", "第三组 burst 结束编号；留空表示不使用第三组。"),
    },
    "裁剪": {
        "enable_crop": (True, "是否执行 RSLC 裁剪；启用后 crop_* 必须由预览图或人工框选给出。"),
        "data_format": ("-", "SLC_copy 数据格式；- 表示使用 GAMMA 默认。"),
        "scale_factor": ("-", "SLC_copy 比例因子；- 表示使用 GAMMA 默认。"),
    },
    "处理方法": {
        "diff_method": ("initial", "差分干涉方法：initial / fourier / unwrapped_ls。"),
        "shp_method": ("HTCI", "SHP 同质像元选择方法：tTest / KSTest / ADTest2 / GLRtest / HTCI。"),
        "phase_opt_method": ("evd_sbas_single", "相位优化方法。"),
        "point_selection_method": ("dsc_pds", "点选取方法：mt_prep_gamma / dsc_select / dsc_pds。"),
        "stamps_mode": ("sbas", "StaMPS 处理模式：ps / sbas / ds。"),
    },
    "地理编码": {
        "range_looks": ("1", "距离向多视数。"),
        "azimuth_looks": ("1", "方位向多视数。"),
        "lat_ovr": ("5", "纬度方向过采样参数。"),
        "lon_ovr": ("5", "经度方向过采样参数。"),
    },
    "RSLC_tab": {
        "rslc_template": ("$1/$1.rslc", "RSLC 数据文件模板，$1 表示日期。"),
        "rslc_par_template": ("$1/$1.rslc.par", "RSLC 参数文件模板，$1 表示日期。"),
    },
    "base_calc": {
        "itab_type": ("1", "itab 类型；1 通常表示单主影像。"),
        "base_calc_plot_flag": ("1", "基线图输出标志。"),
        "bperp_min": ("-", "最小空间基线；- 表示默认。"),
        "bperp_max": ("200", "最大空间基线。"),
        "delta_t_min": ("-", "最小时间基线；- 表示默认。"),
        "delta_t_max": ("37", "最大时间基线；图文流程示例的 SBAS base_calc 使用 37。"),
        "delta_n_max": ("2", "每景影像参与干涉的最大数量。"),
    },
    "RMLI 和差分干涉": {
        "rlks": ("5", "mk_mli_all 和 mk_diff_2d 使用的距离向多视数；图文流程说明常用 5:1。"),
        "azlks": ("1", "mk_mli_all 和 mk_diff_2d 使用的方位向多视数；图文流程说明常用 5:1。"),
        "deformation_file": ("-", "外部形变速率文件；- 表示不使用。"),
        "diff_param_1": ("3", "mk_diff_2d 常规参数。"),
        "diff_s_value": ("2", "mk_diff_2d 的 -s 参数。"),
        "diff_e_value": ("0.1", "mk_diff_2d 的 -e 参数。"),
        "adf_alpha": ("0.35", "ADF 滤波 alpha，仅 unwrapped_ls 使用。"),
        "adf_window": ("32", "ADF 滤波窗口，仅 unwrapped_ls 使用。"),
        "unw_alpha": ("0.35", "解缠 alpha，仅 unwrapped_ls 使用。"),
    },
    "SHP 和相位优化": {
        "cal_win_range": ("15", "SHP 选择窗口距离向大小。"),
        "cal_win_azimuth": ("15", "SHP 选择窗口方位向大小。"),
        "alpha": ("0.05", "SHP 显著性水平。"),
        "phase_opt_output_name": ("phase_opt", "相位优化输出 mat 文件基础名称。"),
        "fit_threshold": ("0.6", "时间相干性或 goodness fit 阈值；图文流程说明 SBAS 通常 0.6，PS 通常 0.4。"),
        "ref_id": ("1", "PS 相位优化使用的主影像序号。"),
        "block_size": ("1", "分块大小；1 表示不分块。"),
    },
    "时序和点选取": {
        "ts_flag": ("1", "file_construct 时序类型：0=PS，1=SBAS。"),
        "psc_da_thresh": ("0.6", "mt_prep_gamma 振幅离差阈值；图文流程说明 SBAS 通常 0.6，PS 通常 0.4。"),
        "rg_patches": ("1", "距离向分块数。"),
        "az_patches": ("1", "方位向分块数。"),
        "rg_overlap": ("50", "距离向重叠像元数。"),
        "az_overlap": ("50", "方位向重叠像元数。"),
    },
    "外部程序": {
        "matlab_command": ("matlab", "MATLAB 命令名或完整路径。"),
        "mt_prep_gamma_addds_command": ("mt_prep_gamma_addDS", "mt_prep_gamma_addDS 命令名或完整路径。"),
    },
    "通知和步骤开关": {
        "skip_unzip": (False, "是否跳过 ZIP 解压。"),
        "skip_generate_slc": (False, "是否跳过 SLC 生成。"),
        "skip_extract_burst": (False, "是否跳过 burst 提取。"),
        "notify_enabled": (True, "是否发送处理通知。"),
        "notify_channel": ("qq_mail", "通知渠道。"),
        "qq_mail_user_env": ("QQ_MAIL_USER", "邮箱账号环境变量名。"),
        "qq_mail_auth_code_env": ("QQ_MAIL_AUTH_CODE", "邮箱授权码环境变量名。"),
        "qq_mail_to_env": ("QQ_MAIL_TO", "收件人环境变量名。"),
    },
}


REQUIRED_USER_INPUTS: dict[str, str] = {
    "task_id": "任务编号，用来区分不同处理任务。",
    "task_root": "任务输出根目录，所有中间结果和结果文件会放在这个目录下。",
    "raw_zip_dir": "Sentinel-1 ZIP 原始数据目录或 ZIP 文件路径。",
    "dem_file": "DEM 文件路径。",
    "master_date": "主影像日期，通常为 YYYYMMDD。",
    "bn_start1": "第一组 burst 起始编号。",
    "bn_end1": "第一组 burst 结束编号。",
    "env_scripts": "执行 GAMMA / MATLAB / StaMPS 前需要 source 的环境脚本列表。",
    "matlab_func_dir": "相位优化、SHP、DSC/PDS 所需 MATLAB 函数根目录。",
}

CROP_REQUIRED_INPUTS: dict[str, str] = {
    "crop_roff": "距离向裁剪起始像元；需要先查看预览图或人工判断裁剪范围，不能使用代码默认值。",
    "crop_nr": "距离向裁剪长度；需要先查看预览图或人工判断裁剪范围，不能使用代码默认值。",
    "crop_loff": "方位向裁剪起始行；需要先查看预览图或人工判断裁剪范围，不能使用代码默认值。",
    "crop_nl": "方位向裁剪长度；需要先查看预览图或人工判断裁剪范围，不能使用代码默认值。",
}

USER_VISIBLE_OPTIONAL_INPUTS: dict[str, str] = {
    "satellite": "数据类型选择，图文流程示例为 S1A；如果数据是 S1B 必须改。",
    "polarization": "极化方式选择，图文流程示例为 VV；如果处理 VH 必须改。",
    "swath": "子波束选择，图文流程示例为 IW1；不同研究区经常需要改。",
    "enable_crop": "是否执行裁剪，默认 true；如果不裁剪需要改成 false。",
    "diff_method": "差分干涉方法选择，默认 initial。",
    "shp_method": "SHP 同质像元方法选择，默认 HTCI。",
    "phase_opt_method": "相位优化方法选择，默认 evd_sbas_single。",
    "point_selection_method": "点选取路线选择，默认 dsc_pds。",
    "stamps_mode": "StaMPS 模式选择，默认 sbas。",
}

FIELD_OPTIONS: dict[str, list[str]] = {
    "satellite": ["S1A", "S1B"],
    "polarization": ["VV", "VH"],
    "swath": ["IW1", "IW2", "IW3", "IW1+IW2", "IW1+IW3", "IW2+IW3", "IW1+IW2+IW3"],
    "enable_crop": ["true", "false"],
    "diff_method": ["initial", "fourier", "unwrapped_ls"],
    "shp_method": ["HTCI", "tTest", "KSTest", "ADTest2", "GLRtest"],
    "phase_opt_method": [
        "evd_sbas_single",
        "emi_sbas_single",
        "evd_ps_single",
        "emi_ps_single",
        "evd_sbas_block",
        "emi_sbas_block",
        "evd_ps_block",
        "emi_ps_block",
    ],
    "point_selection_method": ["dsc_pds", "dsc_select", "mt_prep_gamma"],
    "stamps_mode": ["sbas", "ps", "ds"],
    "skip_unzip": ["true", "false"],
    "skip_generate_slc": ["true", "false"],
    "skip_extract_burst": ["true", "false"],
    "notify_enabled": ["true", "false"],
}


DERIVED_PATH_TEMPLATES: dict[str, str] = {
    # Keep the historical key for backwards-compatible YAML files. Its actual
    # location follows the documented SLC workspace convention.
    "unzip_dir": "{task_root}/SLC",
    "burst_dir": "{task_root}/SLC_select",
    "list_file": "{task_root}/SLC_select/list",
    "geo_dir": "{task_root}/GEO",
    "coreg_dir": "{task_root}/RSLC",
    "crop_dir": "{task_root}/SLC_copy",
    "rslc_dir": "{task_root}/SLC_copy",
    "rslc_tab": "{task_root}/RSLC_tab",
    "bperp_file": "{task_root}/bperp_fileSBAS",
    "itab_file": "{task_root}/itabSBAS",
    "rmli_dir": "{task_root}/RMLI",
    "diff_geo_dir": "{task_root}/GEO_seg",
    "diff_dir": "{task_root}/DIFF",
    "diff2_dir": "{task_root}/DIFF2",
    "shp_output_dir": "{task_root}/SHP",
    "matlab_work_dir": "{task_root}/matlab_scripts",
    "phase_opt_output_dir": "{task_root}/PHASE_OPT",
    "pbase_file": "{task_root}/DIFF/pbase",
}


MASTER_DATE_PATH_TEMPLATES: dict[str, str] = {
    "slc_file": "{burst_dir}/{master_date}/{master_date}.slc",
    "master_rslc_par": "{crop_dir}/{master_date}/{master_date}.rslc.par",
    "rmli_par": "{rmli_dir}/{master_date}.rmli.par",
    "diff_master_rslc": "{crop_dir}/{master_date}/{master_date}.rslc",
    "sar_dem": "{diff_geo_dir}/{master_date}/{master_date}.hgt",
    "master_rmli": "{rmli_dir}/{master_date}.rmli",
}


SATELLITE_OPTIONS = {
    "S1A": "0",
    "A": "0",
    "0": "0",
    "S1B": "1",
    "B": "1",
    "1": "1",
}

POLARIZATION_OPTIONS = {
    "VV": "0",
    "0": "0",
    "VH": "1",
    "1": "1",
}

SWATH_OPTIONS = {
    "IW1": "1",
    "1": "1",
    "IW2": "2",
    "2": "2",
    "IW3": "3",
    "3": "3",
    "IW1+IW2": "4",
    "4": "4",
    "IW1+IW3": "5",
    "5": "5",
    "IW2+IW3": "6",
    "6": "6",
    "IW1+IW2+IW3": "7",
    "7": "7",
}

SATELLITE_LABELS = {"0": "S1A", "1": "S1B"}
POLARIZATION_LABELS = {"0": "VV", "1": "VH"}
SWATH_LABELS = {
    "1": "IW1",
    "2": "IW2",
    "3": "IW3",
    "4": "IW1+IW2",
    "5": "IW1+IW3",
    "6": "IW2+IW3",
    "7": "IW1+IW2+IW3",
}

DEFAULT_DERIVED_CODES = {
    "satellite_code": SATELLITE_OPTIONS[str(DEFAULT_PARAMETER_GROUPS["SLC 数据选择"]["satellite"][0])],
    "polarization_code": POLARIZATION_OPTIONS[
        str(DEFAULT_PARAMETER_GROUPS["SLC 数据选择"]["polarization"][0])
    ],
    "swath_code": SWATH_OPTIONS[str(DEFAULT_PARAMETER_GROUPS["SLC 数据选择"]["swath"][0])],
}


def _flatten_defaults() -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for group in DEFAULT_PARAMETER_GROUPS.values():
        for key, (value, _description) in group.items():
            defaults[key] = value
    return defaults


DEFAULT_TASK_PARAMETERS = _flatten_defaults()


def _is_placeholder(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped.startswith("<") and stripped.endswith(">")


def _clean_user_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in inputs.items():
        if value is None or _is_placeholder(value):
            continue
        if isinstance(value, list):
            items = [item for item in value if item is not None and not _is_placeholder(str(item))]
            if items:
                cleaned[key] = items
            continue
        cleaned[key] = value
    return cleaned


def _normalize_option(value: Any, options: dict[str, str], field_name: str) -> str:
    key = str(value).strip().upper().replace(" ", "")
    if key not in options:
        valid_values = ", ".join(options.keys())
        raise ValueError(f"{field_name} 输入无效：{value}。可选值：{valid_values}")
    return options[key]


def apply_code_defaults(inputs: dict[str, Any]) -> dict[str, Any]:
    user_inputs = _clean_user_inputs(inputs)
    merged = dict(DEFAULT_TASK_PARAMETERS)
    merged.update(user_inputs)

    if "lat_ov" in user_inputs and "lat_ovr" not in user_inputs:
        merged["lat_ovr"] = user_inputs["lat_ov"]

    if "lon_ov" in user_inputs and "lon_ovr" not in user_inputs:
        merged["lon_ovr"] = user_inputs["lon_ov"]

    if "satellite_code" in user_inputs and "satellite" not in user_inputs:
        merged["satellite"] = SATELLITE_LABELS.get(str(user_inputs["satellite_code"]), merged["satellite"])

    if "polarization_code" in user_inputs and "polarization" not in user_inputs:
        merged["polarization"] = POLARIZATION_LABELS.get(
            str(user_inputs["polarization_code"]), merged["polarization"]
        )

    if "swath_code" in user_inputs and "swath" not in user_inputs:
        merged["swath"] = SWATH_LABELS.get(str(user_inputs["swath_code"]), merged["swath"])

    return merged


def apply_derived_codes(inputs: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(inputs)

    if not resolved.get("satellite_code") and resolved.get("satellite"):
        resolved["satellite_code"] = _normalize_option(
            resolved["satellite"], SATELLITE_OPTIONS, "卫星类型"
        )

    if not resolved.get("polarization_code") and resolved.get("polarization"):
        resolved["polarization_code"] = _normalize_option(
            resolved["polarization"], POLARIZATION_OPTIONS, "极化方式"
        )

    if not resolved.get("swath_code") and resolved.get("swath"):
        resolved["swath_code"] = _normalize_option(
            resolved["swath"], SWATH_OPTIONS, "swath"
        )

    return resolved


def apply_derived_paths(inputs: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(inputs)
    if not resolved.get("task_root") and resolved.get("work_dir"):
        resolved["task_root"] = resolved["work_dir"]

    task_root = resolved.get("task_root")
    if not task_root:
        return resolved

    for key, template in DERIVED_PATH_TEMPLATES.items():
        if resolved.get(key):
            continue
        resolved[key] = str(Path(template.format(task_root=task_root)))

    master_date = resolved.get("master_date")
    if not master_date:
        return resolved

    for key, template in MASTER_DATE_PATH_TEMPLATES.items():
        if resolved.get(key):
            continue
        try:
            resolved[key] = str(Path(template.format(**resolved)))
        except KeyError:
            continue

    return resolved


def resolve_effective_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    resolved = apply_code_defaults(inputs)
    resolved = apply_derived_paths(resolved)
    resolved = apply_derived_codes(resolved)
    return resolved


def _format_value(value: Any) -> str:
    if value == "":
        return "<留空>"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _has_value(value: Any) -> bool:
    if value is None or _is_placeholder(value):
        return False
    if isinstance(value, list):
        return any(_has_value(item) for item in value)
    return str(value).strip() != ""


def _is_crop_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "否", "不", "none"}


def describe_code_defaults() -> str:
    lines = [
        "# 当前代码默认参数",
        "",
        "这些值只有在用户没有提供对应字段时才会生效；用户在配置文件、表单或对话里给出的值会覆盖代码默认值。",
        "",
    ]

    for group_name, group in DEFAULT_PARAMETER_GROUPS.items():
        lines.append(f"## {group_name}")
        lines.append("| 字段 | 默认值 | 说明 |")
        lines.append("| --- | --- | --- |")
        for key, (value, description) in group.items():
            lines.append(f"| `{key}` | `{_format_value(value)}` | {description} |")
        lines.append("")

    lines.append("## 必须由用户提供或确认")
    lines.append("| 字段 | 说明 |")
    lines.append("| --- | --- |")
    for key, description in REQUIRED_USER_INPUTS.items():
        lines.append(f"| `{key}` | {description} |")
    lines.append("")

    lines.append("## 启用裁剪时必须由用户提供")
    lines.append("| 字段 | 说明 |")
    lines.append("| --- | --- |")
    for key, description in CROP_REQUIRED_INPUTS.items():
        lines.append(f"| `{key}` | {description} |")
    lines.append("")

    lines.append("## 配置模板中显式保留的选择项")
    lines.append(
        "这些字段虽然有代码默认值，但会影响数据选择或处理路线，建议在配置中保留："
        + ", ".join(f"`{key}`" for key in USER_VISIBLE_OPTIONAL_INPUTS)
        + "。"
    )
    lines.append("")

    lines.append("## 按 task_root 自动推导的路径")
    lines.append("| 字段 | 默认模板 |")
    lines.append("| --- | --- |")
    for key, template in DERIVED_PATH_TEMPLATES.items():
        lines.append(f"| `{key}` | `{template}` |")

    return "\n".join(lines)


def describe_effective_inputs(user_inputs: dict[str, Any]) -> str:
    effective = resolve_effective_inputs(user_inputs)
    clean_user_inputs = _clean_user_inputs(user_inputs)
    user_keys = {
        key
        for key, value in clean_user_inputs.items()
        if not _matches_code_default(key, value)
        and not _matches_friendly_field_code(key, value, clean_user_inputs)
    }
    derived_keys = set(DERIVED_PATH_TEMPLATES) | set(MASTER_DATE_PATH_TEMPLATES) | {
        "satellite_code",
        "polarization_code",
        "swath_code",
        "task_root",
    }

    lines = [
        "# 当前任务最终参数",
        "",
        "来源说明：用户/配置覆盖 > 按 task_root 或选项推导 > 代码默认。",
        "",
        "| 字段 | 当前值 | 来源 |",
        "| --- | --- | --- |",
    ]

    for key in sorted(effective.keys()):
        if key in user_keys:
            source = "用户/配置覆盖"
        elif key in derived_keys:
            source = "自动推导"
        else:
            source = "代码默认"
        lines.append(f"| `{key}` | `{_format_value(effective[key])}` | {source} |")

    missing = missing_required_inputs(user_inputs)
    if missing:
        lines.extend(["", "## 仍需用户提供", ""])
        descriptions = {**REQUIRED_USER_INPUTS, **CROP_REQUIRED_INPUTS}
        lines.extend(f"- `{key}`：{descriptions[key]}" for key in missing)

    return "\n".join(lines)


def _matches_code_default(key: str, value: Any) -> bool:
    if key in DEFAULT_TASK_PARAMETERS:
        return str(value) == str(DEFAULT_TASK_PARAMETERS[key])
    if key in DEFAULT_DERIVED_CODES:
        return str(value) == str(DEFAULT_DERIVED_CODES[key])
    return False


def _matches_friendly_field_code(
    key: str,
    value: Any,
    user_inputs: dict[str, Any],
) -> bool:
    try:
        if key == "satellite_code" and "satellite" in user_inputs:
            return str(value) == _normalize_option(user_inputs["satellite"], SATELLITE_OPTIONS, "卫星类型")
        if key == "polarization_code" and "polarization" in user_inputs:
            return str(value) == _normalize_option(
                user_inputs["polarization"], POLARIZATION_OPTIONS, "极化方式"
            )
        if key == "swath_code" and "swath" in user_inputs:
            return str(value) == _normalize_option(user_inputs["swath"], SWATH_OPTIONS, "swath")
    except ValueError:
        return False
    return False


def missing_required_inputs(inputs: dict[str, Any]) -> list[str]:
    effective = resolve_effective_inputs(inputs)
    missing = [key for key in REQUIRED_USER_INPUTS if not _has_value(effective.get(key))]

    if _is_crop_enabled(effective.get("enable_crop", True)):
        missing.extend(key for key in CROP_REQUIRED_INPUTS if not _has_value(effective.get(key)))

    return missing


def minimal_config_template() -> dict[str, Any]:
    return {
        "task_id": "example_task",
        "workflow_start": "unzip_s1",
        "workflow_end": "stamps_processing",
        "task_root": "<TASK_ROOT>",
        "raw_zip_dir": "<SENTINEL_1_ZIP_DIR_OR_FILE>",
        "dem_file": "<DEM_FILE>",
        "master_date": "<YYYYMMDD>",
        "satellite": DEFAULT_TASK_PARAMETERS["satellite"],
        "polarization": DEFAULT_TASK_PARAMETERS["polarization"],
        "swath": DEFAULT_TASK_PARAMETERS["swath"],
        "bn_start1": "<BURST_START>",
        "bn_end1": "<BURST_END>",
        "enable_crop": DEFAULT_TASK_PARAMETERS["enable_crop"],
        "diff_method": DEFAULT_TASK_PARAMETERS["diff_method"],
        "shp_method": DEFAULT_TASK_PARAMETERS["shp_method"],
        "phase_opt_method": DEFAULT_TASK_PARAMETERS["phase_opt_method"],
        "point_selection_method": DEFAULT_TASK_PARAMETERS["point_selection_method"],
        "stamps_mode": DEFAULT_TASK_PARAMETERS["stamps_mode"],
        "env_scripts": [
            "/home/yu/CONFIG_InSAR.bash",
            "/home/yu/StaMPS_CONFIG.bash",
            "/home/yu/GAMMA.bash",
        ],
        "matlab_func_dir": "<MATLAB_FUNCTION_ROOT>",
    }
