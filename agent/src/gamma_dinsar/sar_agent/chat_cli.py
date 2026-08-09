from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

from langchain_openai import ChatOpenAI

from agent import create_dinsar_agent
from tools import AgentTools


MODEL_NAME = "deepseek-v4-flash"
BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"

DEFAULT_CONFIG_PATH = Path(__file__).parent / "task.yaml"


ACTION_MAP: list[tuple[list[str], str, str]] = [
    (
        ["dsc+pds", "dsc + pds", "pds融合", "ds融合", "ps和ds融合", "dsc pds", "pds_merge", "mt_prep_gamma_addds", "生成pds-ts", "融合dsc和psc"],
        "DSC + PDS 融合",
        "run_dsc_pds_workflow_real",
    ),
    (
        ["dsc选点", "dsc_select", "dsc select", "dsc", "ds候选点", "分布式散射体", "提取dsc", "dsc点", "dsc_select.m", "2.10 dsc"],
        "DSC 选点",
        "run_dsc_select_real",
    ),
    (
        ["stamps", "stamps处理", "stamps(1,7)", "stamps主流程", "stamps 时序", "stamps时序", "sbas stamps", "ps stamps", "ds stamps", "2.11"],
        "StaMPS 处理",
        "run_stamps_processing_real",
    ),
    (
        ["文件组织", "file_construct", "构建ts", "ts组织", "生成ts", "stamps输入文件", "时序文件组织", "整理文件", "组织文件", "2.7"],
        "TS 文件组织",
        "run_file_construct_real",
    ),
    (
        ["相位优化", "evd", "emi", "phase optimization", "phase_opt", "优化相位", "goodness", "goodness fit", "evd_sbas", "2.6"],
        "相位优化",
        "run_phase_optimization_workflow_real",
    ),
    (
        ["shp", "同质像元", "同质像元选取", "alltest_selpoint", "htci", "ttest", "kstest", "adtest", "glrtest", "2.5"],
        "SHP 同质像元选取",
        "run_select_shp_matlab_real",
    ),
    (
        ["差分", "差分干涉", "干涉图", "mk_diff", "mk_diff_2d", "生成diff", "生成差分干涉图", "初始差分", "diff workflow", "2.4"],
        "差分干涉",
        "run_diff_workflow_real",
    ),
    (
        ["rmli", "mk_mli_all", "强度图", "强度文件", "生成rmli", "生成强度", "多视强度", "rmli强度", "rmli.par", "2.3"],
        "生成 RMLI",
        "run_mk_mli_all_real",
    ),
    (
        ["itab", "base_calc", "基线", "生成基线", "计算基线", "bperp", "bperp_file", "干涉对表", "生成itab", "2.2"],
        "生成 itab / 基线文件",
        "run_base_calc_itab_real",
    ),
    (
        ["rslc_tab", "rslctab", "生成rslc_tab", "生成 rslc_tab", "mk_tab", "rslc列表", "rslc文件列表", "建立rslc_tab", "创建rslc_tab", "2.1"],
        "生成 RSLC_tab",
        "write_rslc_tab_from_list_real",
    ),
    (
        ["裁剪", "crop", "slc_copy", "裁剪rslc", "rslc裁剪", "影像裁剪", "裁剪配准影像", "生成crop", "执行裁剪", "运行裁剪"],
        "裁剪 RSLC",
        "run_slc_copy_crop_all_real",
    ),
    (
        ["配准", "coreg", "coregistration", "s1_slc_coreg_multi", "影像配准", "主从配准", "生成coreg", "执行配准", "运行配准", "coreg_multi"],
        "影像配准",
        "run_slc_coreg_multi_real",
    ),
    (
        ["地理编码", "geo", "geocoding", "s1_slc_geo", "主影像地理编码", "重新地理编码", "生成geo", "生成hgt", "slc geo", "地理配准"],
        "地理编码",
        "run_slc_geo_real",
    ),
    (
        ["burst", "brust", "提取burst", "burst提取", "提取 burst", "s1_slc_copy_multi", "裁剪burst", "burst区域", "extract_burst", "slc_select"],
        "Burst 提取",
        "run_extract_burst_real",
    ),
    (
        ["生成slc", "slc生成", "提取slc", "生成 slc", "s1_slc_normal", "转成slc", "slc normal", "运行slc", "执行slc生成", "sentinel-1 slc"],
        "生成 SLC",
        "run_generate_slc_real",
    ),
    (
        ["解压", "unzip", "zip解压", "解压数据", "解压zip", "sentinel-1 zip解压", "原始数据解压", "运行解压", "执行解压", "unzip_s1"],
        "解压 ZIP",
        "run_unzip_s1_real",
    ),
    (
        ["选点", "点选取", "point selection", "候选点提取", "自动选点", "根据point_selection_method", "psc或dsc", "运行选点", "执行选点", "生成点文件"],
        "点选取",
        "run_point_selection_real",
    ),
    (
        ["psc", "mt_prep_gamma", "传统选点", "psc选点", "提取psc", "ps-ts", "ps候选点", "点目标选取", "pscands", "传统ps选点"],
        "PSC 传统选点",
        "run_mt_prep_gamma_real",
    ),
]


def load_getenv_file() -> None:
    getenv_path = Path(__file__).parent / ".getenv"

    if not getenv_path.exists():
        return

    for line in getenv_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and value and key not in os.environ:
            os.environ[key] = value


def build_llm() -> ChatOpenAI:
    api_key = os.environ.get(API_KEY_ENV)

    if not api_key:
        raise RuntimeError(f"未检测到环境变量 {API_KEY_ENV}，请在 .getenv 中设置。")

    return ChatOpenAI(
        model=MODEL_NAME,
        api_key=api_key,
        base_url=BASE_URL,
        temperature=0,
    )


def extract_config_path_from_text(text: str) -> str:
    match = re.search(r"(/[^，,\s]+\.ya?ml)", text)
    if match:
        return match.group(1)

    if "配置文件" in text or "task.yaml" in text or "自己找" in text:
        return str(DEFAULT_CONFIG_PATH)

    return ""


def detect_action(text: str) -> tuple[str, str] | None:
    normalized = text.lower()
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("＋", "+")
    normalized = normalized.replace("，", ",")
    normalized = normalized.replace("。", ".")

    for keywords, title, method_name in ACTION_MAP:
        for keyword in keywords:
            key = keyword.lower().replace(" ", "")
            if key in normalized:
                return title, method_name

    return None


def try_read_parameter_summary(user_input: str, agent_tools: AgentTools) -> str | None:
    normalized = user_input.lower().replace(" ", "")

    default_keywords = [
        "默认参数",
        "默认值",
        "代码默认",
        "当前默认",
        "defaultparameters",
        "defaults",
    ]
    effective_keywords = [
        "最终参数",
        "当前参数",
        "实际参数",
        "有效参数",
        "effectiveparameters",
        "effectiveinputs",
    ]

    logs: list[str] = []
    config_path = extract_config_path_from_text(user_input)

    if config_path:
        logs.append("## 读取配置文件")
        logs.append(agent_tools.load_task_config(config_path))

    if any(keyword in normalized for keyword in default_keywords):
        logs.append(agent_tools.get_default_parameters())
        return "\n\n".join(logs)

    if any(keyword in normalized for keyword in effective_keywords):
        logs.append(agent_tools.get_effective_task_parameters())
        return "\n\n".join(logs)

    return None


def try_run_direct_processing(user_input: str, agent_tools: AgentTools) -> str | None:
    action = detect_action(user_input)

    if action is None:
        return None

    config_path = extract_config_path_from_text(user_input)

    logs: list[str] = []

    if config_path:
        logs.append("## 读取配置文件")
        logs.append(agent_tools.load_task_config(config_path))

    action_title, method_name = action

    if not hasattr(agent_tools, method_name):
        return f"识别到步骤：{action_title}，但 AgentTools 中不存在方法：{method_name}"

    method: Callable[[], str] = getattr(agent_tools, method_name)

    logs.append(f"## 执行步骤：{action_title}")
    logs.append(method())

    return "\n\n".join(logs)


def extract_output(result: Any) -> str:
    if isinstance(result, dict):
        if result.get("output"):
            return str(result["output"])

        messages = result.get("messages", [])
        for message in reversed(messages):
            content = getattr(message, "content", None)
            if content:
                return str(content)

    return str(result)


def main() -> None:
    load_getenv_file()

    print("D-InSAR Agent 启动")
    print(f"当前模型：DeepSeek / {MODEL_NAME}")
    print("输入 exit / quit / q 可以退出。")
    print()

    try:
        llm = build_llm()
    except Exception as exc:
        print(f"Agent 初始化失败：{exc}")
        return

    agent_tools = AgentTools()
    agent = create_dinsar_agent(llm=llm, agent_tools=agent_tools)

    chat_history: list[Any] = []

    while True:
        user_input = input("你：").strip()

        if user_input.lower() in {"exit", "quit", "q"}:
            break

        if not user_input:
            continue

        parameter_summary = try_read_parameter_summary(user_input, agent_tools)

        if parameter_summary is not None:
            print()
            print(f"Agent：{parameter_summary}")
            print()
            continue

        direct_result = try_run_direct_processing(user_input, agent_tools)

        if direct_result is not None:
            print()
            print(f"Agent：{direct_result}")
            print()
            continue

        try:
            result = agent.invoke(
                {
                    "input": user_input,
                    "chat_history": chat_history,
                }
            )

            output = extract_output(result)

            print()
            print(f"Agent：{output}")
            print()

        except Exception as exc:
            print()
            print("调用模型或 Agent 失败。")
            print(f"错误信息：{exc}")
            print()


if __name__ == "__main__":
    main()
