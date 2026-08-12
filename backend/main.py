from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .api_clients import DeepSeekChatClient, SiliconFlowEmbeddingClient
from .config import get_settings
from .file_browser import browse_processing_files
from .prompt_builder import (
    build_system_prompt,
    build_user_prompt,
    build_wrapper_rewrite_prompt,
    classify_query,
    trim_history,
    violates_project_code_answer,
)
from .query_planner import (
    build_query_planner_system_prompt,
    build_query_planner_user_prompt,
    build_rule_based_plan,
    build_vector_query,
    format_plan_for_prompt,
    join_plan_queries,
    merge_query_plans,
    parse_query_plan,
    should_use_llm_planner,
)
from .processing import (
    cancel_processing_job,
    create_processing_task,
    create_processing_job,
    get_processing_defaults,
    preview_processing_config,
    read_processing_job,
    read_processing_task,
)
from .rag_index import CodeRagIndex, GammaRagIndex, build_citations, build_split_context
from .schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ProcessingConfigPreviewResponse,
    ProcessingConfigRequest,
    ProcessingDefaultsResponse,
    ProcessingFileBrowserResponse,
    ProcessingJobCreateRequest,
    ProcessingJobResponse,
    ProcessingTaskCreateRequest,
    ProcessingTaskResponse,
)
from .web_search import (
    WebSearchClient,
    build_web_citations,
    build_web_context,
    build_web_search_query,
    should_use_web_search,
)


@lru_cache(maxsize=1)
def settings():
    return get_settings()


@lru_cache(maxsize=1)
def rag_index():
    return GammaRagIndex(settings())


@lru_cache(maxsize=1)
def code_index():
    return CodeRagIndex(settings())


@lru_cache(maxsize=1)
def embedding_client():
    return SiliconFlowEmbeddingClient(settings())


@lru_cache(maxsize=1)
def chat_client():
    return DeepSeekChatClient(settings())


@lru_cache(maxsize=1)
def web_search_client():
    return WebSearchClient(settings())


app = FastAPI(title="SAR/GAMMA RAG Assistant Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings().allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _missing_config() -> list[str]:
    missing: list[str] = []
    current_settings = settings()
    if not current_settings.siliconflow_api_key:
        missing.append("SILICONFLOW_API_KEY")
    if not current_settings.deepseek_api_key:
        missing.append("DEEPSEEK_API_KEY")
    return missing


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    missing = _missing_config()
    index_loaded = False
    code_index_loaded = False
    try:
        index_loaded = rag_index().is_loaded
    except Exception:
        index_loaded = False
    try:
        code_index_loaded = code_index().is_loaded
    except Exception:
        code_index_loaded = False
    return HealthResponse(
        status="missing_config" if missing else "ok",
        embedding_model=settings().siliconflow_embedding_model,
        chat_model=settings().deepseek_chat_model,
        index_loaded=index_loaded,
        code_index_loaded=code_index_loaded,
        web_search_enabled=settings().web_search_enabled,
        web_search_provider=settings().web_search_provider if settings().web_search_enabled else "disabled",
        missing=missing,
    )


@app.get("/api/processing/defaults", response_model=ProcessingDefaultsResponse)
def processing_defaults() -> ProcessingDefaultsResponse:
    return get_processing_defaults(settings())


@app.get("/api/processing/files", response_model=ProcessingFileBrowserResponse)
def processing_files(path: str | None = None) -> ProcessingFileBrowserResponse:
    try:
        return browse_processing_files(settings(), path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/api/processing/config/preview", response_model=ProcessingConfigPreviewResponse)
def processing_config_preview(request: ProcessingConfigRequest) -> ProcessingConfigPreviewResponse:
    return preview_processing_config(settings(), request.inputs)


@app.post("/api/processing/tasks", response_model=ProcessingTaskResponse)
def processing_task_create(request: ProcessingTaskCreateRequest) -> ProcessingTaskResponse:
    return create_processing_task(settings(), request.inputs)


@app.get("/api/processing/tasks/{task_id}", response_model=ProcessingTaskResponse)
def processing_task_get(task_id: str) -> ProcessingTaskResponse:
    task = read_processing_task(settings(), task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="processing task not found")
    return task


@app.post("/api/processing/jobs", response_model=ProcessingJobResponse)
def processing_job_create(request: ProcessingJobCreateRequest) -> ProcessingJobResponse:
    try:
        return create_processing_job(settings(), request.task_id, workflow=request.workflow)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/processing/tasks/{task_id}/jobs/{job_id}", response_model=ProcessingJobResponse)
def processing_job_get(task_id: str, job_id: str) -> ProcessingJobResponse:
    job = read_processing_job(settings(), task_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="processing job not found")
    return job


@app.post("/api/processing/tasks/{task_id}/jobs/{job_id}/cancel", response_model=ProcessingJobResponse)
def processing_job_cancel(task_id: str, job_id: str) -> ProcessingJobResponse:
    try:
        return cancel_processing_job(settings(), task_id, job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    missing = _missing_config()
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing backend configuration: {', '.join(missing)}")

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    try:
        query_types = classify_query(question)
        rule_plan = build_rule_based_plan(question, query_types)
        plan = rule_plan
        if settings().query_planner_enabled and should_use_llm_planner(question, query_types, rule_plan):
            try:
                raw_plan = chat_client().complete(
                    system_prompt=build_query_planner_system_prompt(),
                    history=trim_history(request.messages, max_turns=2, max_chars_per_turn=350),
                    user_prompt=build_query_planner_user_prompt(question, query_types, rule_plan),
                    max_tokens=settings().query_planner_max_tokens,
                    temperature=0.0,
                )
                plan = merge_query_plans(question, rule_plan, parse_query_plan(raw_plan, rule_plan))
            except Exception:
                plan = rule_plan

        code_focused = plan.answer_mode == "project_code_wrapper"
        query_vector = embedding_client().embed_query(build_vector_query(question, plan))
        manual_top_k = min(settings().top_k, 4) if code_focused else settings().top_k
        code_top_k = max(settings().code_top_k, 6) if code_focused else settings().code_top_k
        manual_query = join_plan_queries(plan.manual_queries)
        code_query = join_plan_queries(plan.code_queries)
        manual_matches = rag_index().search(manual_query, query_vector, top_k=manual_top_k)
        code_matches = code_index().search(code_query, query_vector, top_k=code_top_k)
        matches = [*code_matches, *manual_matches] if plan.prefer_sources[0] == "code" else [*manual_matches, *code_matches]
        rag_context = build_split_context(manual_matches, code_matches, settings().max_context_chars, code_focused=code_focused)

        web_results = []
        if should_use_web_search(settings(), question, query_types, plan, matches):
            web_query = build_web_search_query(question, query_types, plan)
            web_results = web_search_client().search(web_query)
            web_context = build_web_context(web_results)
            if web_context:
                rag_context = f"{rag_context}\n\n{web_context}"

        local_citations = build_citations(matches)
        web_citations = build_web_citations(web_results)
        citations = [*web_citations, *local_citations] if web_citations else local_citations

        answer = chat_client().complete(
            system_prompt=build_system_prompt(),
            history=trim_history(request.messages),
            user_prompt=build_user_prompt(
                question,
                query_types,
                rag_context,
                code_focused=code_focused,
                query_plan=format_plan_for_prompt(plan),
            ),
        )
        if code_focused and violates_project_code_answer(answer):
            answer = chat_client().complete(
                system_prompt=build_system_prompt(),
                history=[],
                user_prompt=build_wrapper_rewrite_prompt(question, query_types, rag_context, answer),
            )
        return ChatResponse(content=answer, queryTypes=query_types, citations=citations)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
