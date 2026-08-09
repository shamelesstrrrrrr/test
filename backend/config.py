from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _resolve_path(value: str, default: str) -> Path:
    candidate = Path(value or default)
    if candidate.is_absolute():
        return candidate
    return PROJECT_ROOT / candidate


def _env_path_list(name: str) -> tuple[Path, ...]:
    raw = _env(name)
    if not raw:
        return ()
    return tuple(Path(item.strip()).expanduser() for item in raw.replace("\n", ",").replace(";", ",").split(",") if item.strip())


def _default_file_browser_roots() -> tuple[Path, ...]:
    candidates = [
        Path.home(),
        PROJECT_ROOT,
        Path("/home"),
        Path("/mnt"),
        Path("/data"),
        Path("/opt"),
        Path("/tmp"),
    ]
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists() and resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


@dataclass(frozen=True)
class BackendSettings:
    allowed_origins: tuple[str, ...]

    siliconflow_api_key: str
    siliconflow_api_base_url: str
    siliconflow_embedding_model: str

    deepseek_api_key: str
    deepseek_api_base_url: str
    deepseek_api_path: str
    deepseek_chat_model: str
    deepseek_temperature: float
    deepseek_max_tokens: int
    query_planner_enabled: bool
    query_planner_max_tokens: int
    web_search_enabled: bool
    web_search_provider: str
    web_search_max_results: int
    web_search_timeout_seconds: int
    web_search_min_score: float

    chunks_jsonl: Path
    sections_jsonl: Path
    index_dir: Path
    document_slug: str
    code_chunks_jsonl: Path
    code_index_dir: Path
    code_document_slug: str
    code_top_k: int
    top_k: int
    lexical_weight: float
    max_context_chars: int
    request_timeout_seconds: int
    processing_tasks_dir: Path
    processing_execution_enabled: bool
    processing_file_browser_roots: tuple[Path, ...]


def get_settings() -> BackendSettings:
    origins = tuple(
        origin.strip()
        for origin in _env(
            "RAG_ALLOWED_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    )

    return BackendSettings(
        allowed_origins=origins,
        siliconflow_api_key=_env("SILICONFLOW_API_KEY"),
        siliconflow_api_base_url=_env("SILICONFLOW_API_BASE_URL", "https://api.siliconflow.cn/v1").rstrip("/"),
        siliconflow_embedding_model=_env("SILICONFLOW_EMBEDDING_MODEL", "BAAI/bge-m3"),
        deepseek_api_key=_env("DEEPSEEK_API_KEY"),
        deepseek_api_base_url=_env("DEEPSEEK_API_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_api_path=_env("DEEPSEEK_API_PATH", "/v1/chat/completions"),
        deepseek_chat_model=_env("DEEPSEEK_CHAT_MODEL", "deepseek-chat"),
        deepseek_temperature=_env_float("DEEPSEEK_TEMPERATURE", 0.2),
        deepseek_max_tokens=_env_int("DEEPSEEK_MAX_TOKENS", 1200),
        query_planner_enabled=_env_bool("QUERY_PLANNER_ENABLED", True),
        query_planner_max_tokens=_env_int("QUERY_PLANNER_MAX_TOKENS", 500),
        web_search_enabled=_env_bool("WEB_SEARCH_ENABLED", True),
        web_search_provider=_env("WEB_SEARCH_PROVIDER", "duckduckgo_lite"),
        web_search_max_results=_env_int("WEB_SEARCH_MAX_RESULTS", 3),
        web_search_timeout_seconds=_env_int("WEB_SEARCH_TIMEOUT_SECONDS", 10),
        web_search_min_score=_env_float("WEB_SEARCH_MIN_SCORE", 0.48),
        chunks_jsonl=_resolve_path(
            _env("RAG_CHUNKS_JSONL"),
            "knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.chunks.jsonl",
        ),
        sections_jsonl=_resolve_path(
            _env("RAG_SECTIONS_JSONL"),
            "knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.sections.jsonl",
        ),
        index_dir=_resolve_path(_env("RAG_INDEX_DIR"), "knowledge/gamma/index"),
        document_slug=_env("RAG_DOCUMENT_SLUG", "gamma_new_user_manual_cn_2019"),
        code_chunks_jsonl=_resolve_path(
            _env("CODE_RAG_CHUNKS_JSONL"),
            "knowledge/code/processing/processing_code_v2_0_2.chunks.jsonl",
        ),
        code_index_dir=_resolve_path(_env("CODE_RAG_INDEX_DIR"), "knowledge/code/index"),
        code_document_slug=_env("CODE_RAG_DOCUMENT_SLUG", "processing_code_v2_0_2"),
        code_top_k=_env_int("CODE_RAG_TOP_K", 4),
        top_k=_env_int("RAG_TOP_K", 6),
        lexical_weight=_env_float("RAG_LEXICAL_WEIGHT", 0.2),
        max_context_chars=_env_int("RAG_MAX_CONTEXT_CHARS", 9000),
        request_timeout_seconds=_env_int("RAG_REQUEST_TIMEOUT_SECONDS", 90),
        processing_tasks_dir=_resolve_path(_env("PROCESSING_TASKS_DIR"), "runtime/processing_tasks"),
        processing_execution_enabled=_env_bool("PROCESSING_EXECUTION_ENABLED", False),
        processing_file_browser_roots=_env_path_list("PROCESSING_FILE_BROWSER_ROOTS") or _default_file_browser_roots(),
    )
