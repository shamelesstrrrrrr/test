from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Literal

from .prompt_builder import (
    DATA_PROCESSING_PATTERN,
    GAMMA_COMMAND_NAME_PATTERN,
    INTERNAL_WORKFLOW_PATTERN,
    MANUAL_COMMAND_PATTERN,
    expand_code_search_query,
    wants_project_code_answer,
)
from .schemas import QueryType


AnswerMode = Literal[
    "manual_guidance",
    "manual_command",
    "project_code_wrapper",
    "internal_workflow",
    "concept",
    "file_layout",
]
SourceName = Literal["manual", "code"]

ALLOWED_ANSWER_MODES: set[str] = {
    "manual_guidance",
    "manual_command",
    "project_code_wrapper",
    "internal_workflow",
    "concept",
    "file_layout",
}
ALLOWED_SOURCES: set[str] = {"manual", "code"}

EXPLICIT_ENTRY_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:[_-][A-Za-z0-9]+)+\b")
COMPLEX_PROCESSING_PATTERN = re.compile(
    r"流程|步骤|如何|怎么|应该|生成|制作|处理|预处理|配准|干涉|差分|解缠|滤波|形变|时序|"
    r"sentinel|tops|alos|terrasar|sbas|psinsar|dinsar|insar",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QueryPlan:
    answer_mode: AnswerMode
    manual_queries: tuple[str, ...]
    code_queries: tuple[str, ...]
    prefer_sources: tuple[SourceName, ...]
    avoid_terms: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    planner_used: bool = False
    confidence: float = 0.0

    def as_prompt_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["manual_queries"] = list(self.manual_queries)
        data["code_queries"] = list(self.code_queries)
        data["prefer_sources"] = list(self.prefer_sources)
        data["avoid_terms"] = list(self.avoid_terms)
        data["missing_information"] = list(self.missing_information)
        return data


def build_rule_based_plan(question: str, query_types: list[QueryType]) -> QueryPlan:
    if wants_project_code_answer(question, query_types):
        return QueryPlan(
            answer_mode="project_code_wrapper",
            manual_queries=(question,),
            code_queries=(expand_code_search_query(question),),
            prefer_sources=("code", "manual"),
            avoid_terms=(
                "前置条件",
                "处理步骤",
                "步骤 1",
                "create_diff_par",
                "rdc_trans",
                "SLC_intf",
            ),
            confidence=0.74,
        )

    if INTERNAL_WORKFLOW_PATTERN.search(question):
        return QueryPlan(
            answer_mode="internal_workflow",
            manual_queries=(question,),
            code_queries=(question,),
            prefer_sources=("manual", "code"),
            confidence=0.82,
        )

    if GAMMA_COMMAND_NAME_PATTERN.search(question) and MANUAL_COMMAND_PATTERN.search(question):
        return QueryPlan(
            answer_mode="manual_command",
            manual_queries=(question,),
            code_queries=(question,),
            prefer_sources=("manual", "code"),
            confidence=0.88,
        )

    if "file_layout" in query_types and "workflow" not in query_types:
        return QueryPlan(
            answer_mode="file_layout",
            manual_queries=(question,),
            code_queries=(question,),
            prefer_sources=("manual", "code"),
            confidence=0.72,
        )

    if "concept" in query_types and "workflow" not in query_types and "command" not in query_types:
        return QueryPlan(
            answer_mode="concept",
            manual_queries=(question,),
            code_queries=(question,),
            prefer_sources=("manual", "code"),
            confidence=0.72,
        )

    return QueryPlan(
        answer_mode="manual_guidance",
        manual_queries=(question,),
        code_queries=(question,),
        prefer_sources=("manual", "code"),
        confidence=0.58,
    )


def should_use_llm_planner(question: str, query_types: list[QueryType], rule_plan: QueryPlan) -> bool:
    if rule_plan.answer_mode in {"manual_command", "internal_workflow", "concept", "file_layout"}:
        return False
    if GAMMA_COMMAND_NAME_PATTERN.search(question) and MANUAL_COMMAND_PATTERN.search(question):
        return False
    if EXPLICIT_ENTRY_PATTERN.search(question) and MANUAL_COMMAND_PATTERN.search(question):
        return False
    if rule_plan.answer_mode == "project_code_wrapper" and COMPLEX_PROCESSING_PATTERN.search(question):
        return True
    if "workflow" in query_types and DATA_PROCESSING_PATTERN.search(question):
        return True
    return len(question) >= 36 and any(query_type in query_types for query_type in ("workflow", "code_template"))


def build_query_planner_system_prompt() -> str:
    schema = {
        "answer_mode": "manual_guidance | manual_command | project_code_wrapper | internal_workflow | concept | file_layout",
        "manual_queries": ["用于检索 GAMMA 手册的短查询，不超过 4 条"],
        "code_queries": ["用于检索 version2.0.2 代码库的短查询，不超过 4 条"],
        "prefer_sources": ["manual 或 code，按优先级排序"],
        "avoid_terms": ["回答中应避免的内部命令或结构词"],
        "missing_information": ["需要用户补充的信息；没有则为空数组"],
        "confidence": 0.0,
    }
    return "\n".join(
        [
            "你只负责为 SAR/GAMMA 学习助手生成 RAG 检索计划，不回答用户问题。",
            "必须只输出一个 JSON 对象，不要输出 Markdown、解释、代码块或多余文本。",
            "如果用户问数据处理怎么做、如何生成结果、用哪个流程，默认规划为 project_code_wrapper，优先检索项目封装脚本/函数。",
            "如果问题包含两景 SLC、干涉图、差分干涉或形变图，code_queries 应优先包含 DInSAR_complete_Quick、DInSAR_complete、D-InSAR_TX、DIFF_process_nogeocode 等封装入口候选。",
            "如果用户明确询问某个官方 GAMMA 命令的参数、格式、语法，规划为 manual_command，优先检索 GAMMA 手册。",
            "如果用户明确要求内部流程、底层步骤、原理或展开每一步，规划为 internal_workflow。",
            "project_code_wrapper 模式下，avoid_terms 应加入 create_diff_par、rdc_trans、SLC_intf 等内部命令词，避免最终回答展开内部流程。",
            "查询词要短而具体，可以加入中英文同义词、脚本名、命令名，但不要编造不存在的精确参数顺序。",
            "JSON 结构示例：",
            json.dumps(schema, ensure_ascii=False, indent=2),
        ]
    )


def build_query_planner_user_prompt(
    question: str,
    query_types: list[QueryType],
    rule_plan: QueryPlan,
) -> str:
    return "\n".join(
        [
            f"用户问题：{question}",
            f"规则识别的问题类型：{', '.join(query_types)}",
            "规则初判计划：",
            json.dumps(rule_plan.as_prompt_dict(), ensure_ascii=False, indent=2),
            "请在遵守规则初判的基础上，输出更适合检索的 JSON 计划。",
        ]
    )


def parse_query_plan(raw_text: str, fallback: QueryPlan) -> QueryPlan:
    payload = _extract_json_object(raw_text)
    if payload is None:
        return fallback

    answer_mode = _clean_answer_mode(payload.get("answer_mode"), fallback.answer_mode)
    prefer_sources = _clean_sources(payload.get("prefer_sources"), fallback.prefer_sources)
    manual_queries = _clean_text_list(payload.get("manual_queries"), fallback.manual_queries, max_items=4)
    code_queries = _clean_text_list(payload.get("code_queries"), fallback.code_queries, max_items=4)
    avoid_terms = _clean_text_list(payload.get("avoid_terms"), fallback.avoid_terms, max_items=8)
    missing_information = _clean_text_list(
        payload.get("missing_information"),
        fallback.missing_information,
        max_items=4,
    )
    confidence = _clean_confidence(payload.get("confidence"), fallback.confidence)

    return QueryPlan(
        answer_mode=answer_mode,
        manual_queries=manual_queries,
        code_queries=code_queries,
        prefer_sources=prefer_sources,
        avoid_terms=avoid_terms,
        missing_information=missing_information,
        planner_used=True,
        confidence=confidence,
    )


def merge_query_plans(question: str, rule_plan: QueryPlan, llm_plan: QueryPlan) -> QueryPlan:
    if not llm_plan.planner_used:
        return rule_plan
    if rule_plan.answer_mode in {"manual_command", "internal_workflow"}:
        return rule_plan

    answer_mode = llm_plan.answer_mode
    if rule_plan.answer_mode == "project_code_wrapper":
        answer_mode = "project_code_wrapper"

    prefer_sources = llm_plan.prefer_sources or rule_plan.prefer_sources
    if answer_mode == "project_code_wrapper":
        prefer_sources = ("code", "manual")

    manual_queries = _unique_texts((question, *llm_plan.manual_queries, *rule_plan.manual_queries), max_items=6)
    code_base_queries = (question, *llm_plan.code_queries, *rule_plan.code_queries)
    if answer_mode == "project_code_wrapper":
        expanded_query = expand_code_search_query(question)
        code_base_queries = (question, expanded_query, *rule_plan.code_queries, *llm_plan.code_queries)
    code_queries = _unique_texts(code_base_queries, max_items=8)

    avoid_terms = _unique_texts((*rule_plan.avoid_terms, *llm_plan.avoid_terms), max_items=10)
    return replace(
        llm_plan,
        answer_mode=answer_mode,  # type: ignore[arg-type]
        manual_queries=manual_queries,
        code_queries=code_queries,
        prefer_sources=prefer_sources,
        avoid_terms=avoid_terms,
    )


def join_plan_queries(queries: tuple[str, ...], max_chars: int = 2200) -> str:
    text = "\n".join(_unique_texts(queries, max_items=6))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 16] + "\n[已截断]"


def build_vector_query(question: str, plan: QueryPlan, max_chars: int = 1600) -> str:
    if plan.answer_mode == "project_code_wrapper":
        queries = (question, *plan.code_queries[:3], *plan.manual_queries[:1])
    else:
        queries = (question, *plan.manual_queries[:3], *plan.code_queries[:1])
    return join_plan_queries(_unique_texts(queries, max_items=5), max_chars=max_chars)


def format_plan_for_prompt(plan: QueryPlan) -> str:
    return "\n".join(
        [
            f"answer_mode: {plan.answer_mode}",
            f"planner_used: {str(plan.planner_used).lower()}",
            f"confidence: {plan.confidence:.2f}",
            f"prefer_sources: {', '.join(plan.prefer_sources)}",
            f"manual_queries: {' | '.join(plan.manual_queries) or 'N/A'}",
            f"code_queries: {' | '.join(plan.code_queries) or 'N/A'}",
            f"avoid_terms: {' | '.join(plan.avoid_terms) or 'N/A'}",
        ]
    )


def _extract_json_object(raw_text: str) -> dict[str, object] | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start < 0 or end <= start:
        return None
    candidate = raw_text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clean_answer_mode(value: object, fallback: AnswerMode) -> AnswerMode:
    if isinstance(value, str) and value in ALLOWED_ANSWER_MODES:
        return value  # type: ignore[return-value]
    return fallback


def _clean_sources(value: object, fallback: tuple[SourceName, ...]) -> tuple[SourceName, ...]:
    if not isinstance(value, list):
        return fallback
    sources: list[SourceName] = []
    for item in value:
        if isinstance(item, str) and item in ALLOWED_SOURCES and item not in sources:
            sources.append(item)  # type: ignore[arg-type]
    return tuple(sources) or fallback


def _clean_text_list(value: object, fallback: tuple[str, ...], max_items: int) -> tuple[str, ...]:
    if not isinstance(value, list):
        return fallback
    return _unique_texts((str(item) for item in value if isinstance(item, str)), max_items=max_items) or fallback


def _unique_texts(values: tuple[str, ...] | list[str] | object, max_items: int) -> tuple[str, ...]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:  # type: ignore[union-attr]
        text = re.sub(r"\s+", " ", str(value)).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text[:500])
        if len(cleaned) >= max_items:
            break
    return tuple(cleaned)


def _clean_confidence(value: object, fallback: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(0.0, min(1.0, confidence))
