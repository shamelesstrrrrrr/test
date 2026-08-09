from __future__ import annotations

import re

from .schemas import ChatTurn, QueryType


CODE_FOCUS_PATTERN = re.compile(
    r"数据处理|处理数据|预处理|脚本|封装|代码|函数|入口|调用|用法|version|pre_process|s1_slc|coreg|怎么用|如何使用",
    re.IGNORECASE,
)

DATA_PROCESSING_PATTERN = re.compile(
    r"流程|步骤|如何|怎么|怎么做|处理|生成|制作|配准|预处理|地理编码|干涉|差分|解缠|滤波|形变|时序|"
    r"slc|rslc|dem|tops|sentinel|alos|terrasar|sbas|psinsar|dinsar",
    re.IGNORECASE,
)

INTERNAL_WORKFLOW_PATTERN = re.compile(
    r"内部流程|内部步骤|底层流程|详细流程|完整流程|展开流程|展开步骤|原理|每一步|gamma\s*步骤|gamma\s*流程",
    re.IGNORECASE,
)

GAMMA_COMMAND_NAME_PATTERN = re.compile(
    r"\b(create_diff_par|create_offset|create_offset_SLC|par_S1_SLC|rdc_trans|offset_pwr|offset_pwrm|"
    r"offset_fit|offset_fitm|interp_cpx|interp_real|SLC_intf|SLC_diff_intf|SLC_interp|S1_coreg_TOPS|"
    r"SLC_tab|SLC_mosaic_S1_TOPS|SLC_copy|mk_diff_2d|rasmph|rascc|base_calc|multi_look)\b",
    re.IGNORECASE,
)

MANUAL_COMMAND_PATTERN = re.compile(
    r"命令|参数|格式|语法|用法|解释|怎么用|如何使用",
    re.IGNORECASE,
)

INTERNAL_ANSWER_PATTERN = re.compile(
    r"前置条件|处理步骤|步骤\s*[0-9一二三四五六七八九十]+|生成\s*DIFF/GEO|"
    r"\b(create_diff_par|rdc_trans|offset_pwr|offset_pwrm|offset_fit|offset_fitm|interp_cpx|interp_real|"
    r"SLC_intf|SLC_diff_intf|mk_tab|base_calc|mk_mli_all|mk_diff_2d|mk_adf_2d|mk_unw_2d|"
    r"set_value|rasmph|rascc)\b",
    re.IGNORECASE,
)


def wants_project_code_answer(question: str, query_types: list[QueryType] | None = None) -> bool:
    if INTERNAL_WORKFLOW_PATTERN.search(question):
        return False
    has_gamma_command = bool(GAMMA_COMMAND_NAME_PATTERN.search(question))
    if has_gamma_command and MANUAL_COMMAND_PATTERN.search(question):
        return False
    if CODE_FOCUS_PATTERN.search(question):
        return True
    if query_types and "workflow" in query_types and DATA_PROCESSING_PATTERN.search(question):
        return True
    return False


def expand_code_search_query(question: str) -> str:
    hints: list[str] = []
    if re.search(r"干涉|差分|形变|解缠|滤波|diff|dinsar|interfer", question, re.IGNORECASE):
        hints.extend(
            [
                "DIFF_process_nogeocode",
                "DInSAR_complete",
                "DInSAR_complete_Quick",
                "D-InSAR_ALOS",
                "D-InSAR_TX",
                "D-InSAR_RADA2",
                "RSLC_DIR master_slc.par rlks azlks hgt cc_threshold pwr_threshold",
            ]
        )
    if re.search(r"sentinel|s1|tops|预处理|配准|rslc|coreg", question, re.IGNORECASE):
        hints.extend(
            [
                "S1_SLC_COREG",
                "S1_SLC_COREG_Multi",
                "S1_SLC_Normal",
                "S1_SLC_GEO",
                "Sentinel-1_SLC_Coreg",
                "Sentinel-1_SLC_Geocode",
                "UNZIP_SLC_DIR GEO_DIR list_file pol swath COREG_DIR",
            ]
        )
    if re.search(r"stamps|sbas|psinsar|ps|时序|文件组织|组织", question, re.IGNORECASE):
        hints.extend(
            [
                "file_construct",
                "STAMPSGO",
                "PDS_Merge",
                "GEO_DIR ts_flag SLC_DIR DIFF_DIR base_dir list_file bperp_file RMLI_DIR",
            ]
        )
    if not hints:
        return question
    return f"{question}\n{' '.join(hints)}"


def violates_project_code_answer(answer: str) -> bool:
    return bool(INTERNAL_ANSWER_PATTERN.search(answer))


def classify_query(question: str) -> list[QueryType]:
    normalized = question.lower()
    types: set[QueryType] = set()

    if re.search(r"什么是|何为|概念|基础|insar|sar|相干|相位", normalized):
        types.add("concept")
    if re.search(r"流程|步骤|如何|怎么做|生成|workflow|处理目标|数据处理|处理数据|预处理|封装|脚本|方法|coreg|pre_process|s1_slc", normalized):
        types.add("workflow")
    if re.search(r"命令|gamma|slc_intf|create_offset|command|[_][a-z0-9]|[a-z0-9][_]", normalized):
        types.add("command")
    if re.search(r"参数|必填|输入|输出|类型|parameter", normalized):
        types.add("parameter")
    if re.search(r"目录|文件|路径|放置|layout", normalized):
        types.add("file_layout")
    if re.search(r"代码|模板|python|命令行|code|数据处理|处理数据|预处理|脚本|函数|封装|version|coreg|pre_process|s1_slc", normalized):
        types.add("code_template")

    return sorted(types) or ["concept"]


def build_system_prompt() -> str:
    return "\n".join(
        [
            "你是面向学生的 SAR/GAMMA 影像处理知识与流程指导助手。",
            "你只提供知识解释、流程指导、目录建议、命令说明和占位符代码模板，回答要短而实用。",
            "禁止执行 GAMMA、禁止执行 Shell、禁止使用 SSH、禁止连接 MCP Server。",
            "涉及 GAMMA 官方命令语法、参数顺序和输入输出关系时，必须以 GAMMA 手册证据为准；不得编造手册名称、页码、章节、命令或参数顺序。",
            "涉及 version2.0.2 项目封装脚本、函数和处理入口时，必须优先依据 evidence_type=code 的代码库证据回答；GAMMA 手册只作为辅助验证。",
            "涉及网页搜索 evidence_type=web 时，只能把它作为通用 SAR/InSAR 背景、最新资料或本地证据不足时的补充；不得用网页搜索结果替代 GAMMA 手册来确认官方命令参数顺序。",
            "如果检索证据不足以确认某个命令、参数、输入输出关系或精确顺序，必须明确写在“未确认内容”中。",
            "代码模板必须使用占位符，例如 <PROJECT_ROOT>、<REFERENCE_SLC>、<OUTPUT_INTERFEROGRAM>，不得伪造用户真实路径。",
            "回答必须使用中文 Markdown，优先给出可直接学习和使用的信息，避免背景铺垫、客套话、重复免责声明和过长解释。",
            "不要使用 emoji 或装饰性特殊符号。",
        ]
    )


def _type_note(query_types: list[QueryType], code_focused: bool) -> str:
    if code_focused:
        return "\n".join(
            [
                "这是项目处理代码/封装脚本类问题。",
                "回答应优先给出 version2.0.2 中封装好的脚本或函数，而不是展开完整内部 GAMMA 流程。",
                "必须包含：推荐使用的封装脚本/函数、它是做什么的、适用场景、输入参数表、主要输出、最小占位符示例、注意事项、引用来源。",
                "如果有多个候选，选择一个最匹配的主入口展开说明；备选入口最多 2 个，每个只用一行说明适用差异，不要为多个脚本都展开完整参数表。",
                "回答结构必须围绕“封装命令/脚本入口”组织；不要使用“前置条件、处理步骤、步骤 1、步骤 2”这种内部流程结构。",
                "只在用户明确要求“内部流程/原理/展开步骤”时，才解释脚本内部调用的 GAMMA 步骤；否则用一句话概括内部封装即可。",
                "不要输出封装脚本内部的 GAMMA/辅助命令名称、完整命令行或精确参数串；如果需要提到内部调用，只写“内部封装了若干处理步骤”这种概括。",
                "示例只给封装脚本或函数的最小调用形式和交互输入占位符；不要加入 mkdir、cd、cat、文件写入、批处理准备等 Shell 操作。",
                "注意事项最多 3 条，未确认内容最多 2 条，不要写背景铺垫、长篇标题或重复免责声明。",
                "如果代码证据不足以确认某个输入或输出，放到“未确认内容”，不要猜。",
                "回答尽量控制在 450 字以内。",
            ]
        )

    notes: list[str] = []
    if "workflow" in query_types:
        notes.append(
            "如果是流程问题，回答应包含：处理目标、前置条件、处理步骤、每步输入、每步输出、可能使用的命令、推荐目录、注意事项、引用来源。"
        )
    if "command" in query_types or "parameter" in query_types:
        notes.append(
            "如果是命令或参数问题，回答应包含：命令用途、命令格式、参数表、输入文件、输出文件、示例代码、未确认内容、引用来源。"
        )
    if "code_template" in query_types:
        notes.append("如果生成代码模板，只能使用占位符路径和占位符参数，不要生成真实路径，也不要实际执行命令。")
    if "file_layout" in query_types:
        notes.append("如果回答目录组织，必须使用 <PROJECT_ROOT> 这类占位符，并说明原始数据、DEM、SLC、参数文件、干涉图和结果文件的推荐位置。")
    notes.append(
        "如果“项目处理代码证据 code”中有相关片段，可以简要说明项目封装脚本；不要展开用户没有要求的内部流程。"
    )
    notes.append("回答尽量控制在 1000 字以内。")
    return "\n".join(notes) or "按照问题类型组织答案，并保持引用可核验。"


def build_user_prompt(
    question: str,
    query_types: list[QueryType],
    rag_context: str,
    code_focused: bool = False,
    query_plan: str | None = None,
) -> str:
    answer_mode = "project_code_wrapper" if code_focused else "manual_guidance"
    plan_section = f"""
查询规划：
{query_plan}
""" if query_plan else ""
    return f"""用户问题：
{question}

识别到的问题类型：
{", ".join(query_types)}

回答模式：
{answer_mode}
{plan_section}

回答格式要求：
{_type_note(query_types, code_focused)}

已检索到的 RAG 证据：
{rag_context}

请根据以上证据回答。每个关键结论尽量标注引用编号，例如 [S1]、[S2]；网页补充证据使用 [W1]、[W2]。
证据分为三类：
1. evidence_type=manual：GAMMA 手册证据，用于确认官方命令、参数顺序、输入输出和页码。
2. evidence_type=code：项目处理代码证据，用于说明 version2.0.2 中自定义脚本、函数或封装流程如何把多个 GAMMA 步骤组织成一个处理方法。
3. evidence_type=web：网页搜索补充证据，只用于通用概念、背景资料或本地证据不足时的辅助说明。

回答时必须同时处理这些证据：
- 如果回答模式是 project_code_wrapper，优先回答封装脚本/函数怎么用：脚本名、用途、输入、输出、最小示例和注意事项；不要展开完整内部流程，也不要贴出封装脚本内部的完整 GAMMA 命令行或参数串。
- project_code_wrapper 模式下只展开一个最匹配的主入口；如果需要列备选入口，最多列 2 个短行，不要展开多个脚本的完整参数表。
- 如果代码证据中出现相关自定义脚本或函数，请明确写出它的脚本名/函数名、输入参数、输出目录或文件。内部 GAMMA 调用只用一句话概括，除非用户明确要求展开。
- 不要把代码证据当成 GAMMA 官方语法；涉及精确命令参数顺序时仍以 manual 为准。
- 不要把网页证据当成 GAMMA 官方语法；如果只从 web 找到资料，必须写清“网页补充，未由本地手册验证”。
如果证据中没有出现某个命令或参数，不要猜测；请明确说明无法确认。"""


def build_wrapper_rewrite_prompt(
    question: str,
    query_types: list[QueryType],
    rag_context: str,
    previous_answer: str,
) -> str:
    return f"""用户问题：
{question}

识别到的问题类型：{", ".join(query_types)}

上一版回答违反了“封装脚本优先”的规则，出现了内部 GAMMA 流程或内部命令。请重新回答，只保留 version2.0.2 中封装入口的使用说明。

强制要求：
1. 第一行直接给出“推荐封装入口”，只能写脚本/函数名和相对路径。
2. 不要写“前置条件”“处理步骤”“步骤 1/2/3”。
3. 不要列出 create_diff_par、rdc_trans、offset_pwrm、SLC_intf、base_calc、set_value、mk_diff_2d 等内部 GAMMA/辅助命令；除非它们本身就是用户明确询问的封装入口。
4. 必须包含：封装入口、用途、输入参数表、主要输出、最小占位符调用示例、未确认内容、引用来源。
5. 如果检索不到合适的封装脚本，明确写“未在代码库证据中确认封装入口”，不要退回手册内部流程。
6. 控制在 500 字以内。

RAG 证据：
{rag_context}

上一版违规回答，仅用于判断要删除哪些内容，不要照抄：
{_compact_turn_text(previous_answer, 1600)}
"""


def _compact_turn_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 20]}... [已截断]"


def trim_history(messages: list[ChatTurn], max_turns: int = 4, max_chars_per_turn: int = 700) -> list[ChatTurn]:
    cleaned = [
        ChatTurn(role=turn.role, content=_compact_turn_text(turn.content, max_chars_per_turn))
        for turn in messages
        if turn.role in {"user", "assistant"} and turn.content.strip()
    ]
    return cleaned[-max_turns:]
