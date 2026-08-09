from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .config import BackendSettings
from .schemas import Citation


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def _compact_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    head = max_chars // 2
    tail = max_chars - head
    return f"{compact[:head]} ... {compact[-tail:]}"


def _page_label(pages: list[int] | None, page_start: int | None, page_end: int | None) -> str:
    if pages:
        if len(pages) == 1:
            return f"p. {pages[0]}"
        return f"pp. {min(pages)}-{max(pages)}"
    if page_start and page_end:
        return f"p. {page_start}" if page_start == page_end else f"pp. {page_start}-{page_end}"
    return "N/A"


def _line_label(record: dict[str, Any]) -> str:
    line_start = record.get("line_start")
    line_end = record.get("line_end")
    if line_start and line_end:
        return f"L{line_start}" if line_start == line_end else f"L{line_start}-L{line_end}"
    return "N/A"


def _extract_query_terms(query: str) -> tuple[set[str], list[str]]:
    ascii_terms = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_./-]*|\d+(?:\.\d+)?", query)
    }
    chinese_phrases = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    return ascii_terms, chinese_phrases


def _score_lexical_match(query: str, record: dict[str, Any], chunk: dict[str, Any]) -> float:
    ascii_terms, chinese_phrases = _extract_query_terms(query)
    command_name = (record.get("command_name") or "").lower()
    commands_detected = " ".join(record.get("commands_detected") or []).lower()
    section_title = (record.get("section_title") or "").lower()
    heading_path = " ".join(record.get("heading_path") or []).lower()
    relative_path = (record.get("relative_path") or "").lower()
    text = chunk.get("text") or ""
    lower_text = text.lower()

    score = 0.0
    for term in ascii_terms:
        if command_name:
            if term == command_name:
                score += 1.8
            elif term in command_name or command_name in term:
                score += 1.0
        if term in commands_detected:
            score += 0.9
        if term in section_title or term in heading_path:
            score += 0.35
        if term in relative_path:
            score += 0.45
        if term in lower_text:
            score += 0.25
            if "_" in term:
                score += 0.45

    for phrase in chinese_phrases:
        if phrase in text:
            score += 0.25
        if phrase in record.get("section_title", ""):
            score += 0.25

    return min(score, 3.0)


@dataclass(frozen=True)
class RagMatch:
    index: int
    combined_score: float
    vector_score: float
    lexical_score: float
    record: dict[str, Any]
    chunk: dict[str, Any]
    parent_section: dict[str, Any] | None
    evidence_type: str = "manual"

    def citation(self, rank: int) -> Citation:
        command_name = self.record.get("command_name") or "N/A"
        page = (
            _line_label(self.record)
            if self.evidence_type == "code"
            else _page_label(self.record.get("pages"), self.record.get("page_start"), self.record.get("page_end"))
        )
        verification_status = (
            "code_reference"
            if self.evidence_type == "code"
            else "manual_verified"
            if self.vector_score >= 0.55 or self.lexical_score > 0
            else "partial_manual_evidence"
        )
        citation_prefix = "code" if self.evidence_type == "code" else "manual"
        return Citation(
            id=f"{citation_prefix}-{rank:02d}-{self.record['chunk_id']}",
            source=self.chunk.get("source") or "GAMMA软件新用户手册中文版-2019.pdf",
            page=page,
            command_name=command_name,
            section=self.record.get("section_title") or "N/A",
            verification_status=verification_status,
            retrieval_score=round(self.combined_score, 4),
            excerpt=_compact_text(self.chunk.get("text") or "", 650),
        )

    def prompt_context(self, rank: int, max_chars: int) -> str:
        chunk_text = self.chunk.get("text") or ""
        parent_text = ""
        if self.parent_section:
            parent_text = self.parent_section.get("text") or ""

        if parent_text and len(parent_text) <= max_chars and chunk_text.strip() in parent_text:
            context_text = parent_text
        else:
            context_text = chunk_text

        heading_path = " > ".join(self.record.get("heading_path") or [])
        return "\n".join(
            [
                f"[S{rank}]",
                f"evidence_type: {self.evidence_type}",
                f"source: {self.chunk.get('source') or 'GAMMA软件新用户手册中文版-2019.pdf'}",
                f"page_or_lines: {_line_label(self.record) if self.evidence_type == 'code' else _page_label(self.record.get('pages'), self.record.get('page_start'), self.record.get('page_end'))}",
                f"command_name: {self.record.get('command_name') or 'N/A'}",
                f"commands_detected: {', '.join(self.record.get('commands_detected') or []) or 'N/A'}",
                f"section: {self.record.get('section_title') or 'N/A'}",
                f"heading_path: {heading_path or 'N/A'}",
                f"score: {self.combined_score:.4f} (vector={self.vector_score:.4f}, lexical={self.lexical_score:.4f})",
                "excerpt:",
                _compact_text(context_text, max_chars),
            ]
        )


class GammaRagIndex:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings
        self.embeddings: np.ndarray | None = None
        self.records: list[dict[str, Any]] = []
        self.chunks_by_id: dict[str, dict[str, Any]] = {}
        self.sections_by_id: dict[str, dict[str, Any]] = {}
        self.manifest: dict[str, Any] = {}
        self.load()

    @property
    def is_loaded(self) -> bool:
        return self.embeddings is not None and len(self.records) > 0 and len(self.chunks_by_id) > 0

    def load(self) -> None:
        slug = self.settings.document_slug
        embeddings_path = self.settings.index_dir / f"{slug}.embeddings.npy"
        records_path = self.settings.index_dir / f"{slug}.embedding_records.jsonl"
        manifest_path = self.settings.index_dir / f"{slug}.embedding_manifest.json"

        self.embeddings = np.load(embeddings_path)
        self.records = _read_jsonl(records_path)
        self.chunks_by_id = {chunk["chunk_id"]: chunk for chunk in _read_jsonl(self.settings.chunks_jsonl)}
        self.sections_by_id = {
            section["section_id"]: section
            for section in _read_jsonl(self.settings.sections_jsonl)
        }
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if self.embeddings.ndim != 2 or self.embeddings.shape[0] != len(self.records):
            raise RuntimeError(
                f"Embedding index mismatch: embeddings={self.embeddings.shape}, records={len(self.records)}"
            )

    def search(self, query: str, query_vector: np.ndarray, top_k: int | None = None) -> list[RagMatch]:
        if self.embeddings is None:
            raise RuntimeError("RAG index is not loaded")

        scores = self.embeddings @ query_vector
        matches: list[RagMatch] = []
        for index, vector_score in enumerate(scores):
            record = self.records[index]
            chunk = self.chunks_by_id.get(record["chunk_id"], {})
            lexical_score = _score_lexical_match(query, record, chunk)
            combined_score = float(vector_score) + self.settings.lexical_weight * lexical_score
            matches.append(
                RagMatch(
                    index=index,
                    combined_score=combined_score,
                    vector_score=float(vector_score),
                    lexical_score=lexical_score,
                    record=record,
                    chunk=chunk,
                    parent_section=self.sections_by_id.get(record.get("section_id")),
                    evidence_type="manual",
                )
            )

        matches.sort(key=lambda match: match.combined_score, reverse=True)
        return matches[: top_k or self.settings.top_k]


class CodeRagIndex:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings
        self.embeddings: np.ndarray | None = None
        self.records: list[dict[str, Any]] = []
        self.chunks_by_id: dict[str, dict[str, Any]] = {}
        self.manifest: dict[str, Any] = {}
        self.load()

    @property
    def is_loaded(self) -> bool:
        return self.embeddings is not None and len(self.records) > 0 and len(self.chunks_by_id) > 0

    def load(self) -> None:
        slug = self.settings.code_document_slug
        embeddings_path = self.settings.code_index_dir / f"{slug}.embeddings.npy"
        records_path = self.settings.code_index_dir / f"{slug}.embedding_records.jsonl"
        manifest_path = self.settings.code_index_dir / f"{slug}.embedding_manifest.json"

        self.embeddings = np.load(embeddings_path)
        self.records = _read_jsonl(records_path)
        self.chunks_by_id = {chunk["chunk_id"]: chunk for chunk in _read_jsonl(self.settings.code_chunks_jsonl)}
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        if self.embeddings.ndim != 2 or self.embeddings.shape[0] != len(self.records):
            raise RuntimeError(
                f"Code embedding index mismatch: embeddings={self.embeddings.shape}, records={len(self.records)}"
            )

    def search(self, query: str, query_vector: np.ndarray, top_k: int | None = None) -> list[RagMatch]:
        if self.embeddings is None:
            raise RuntimeError("Code RAG index is not loaded")

        scores = self.embeddings @ query_vector
        matches: list[RagMatch] = []
        for index, vector_score in enumerate(scores):
            record = self.records[index]
            chunk = self.chunks_by_id.get(record["chunk_id"], {})
            lexical_score = _score_lexical_match(query, record, chunk)
            combined_score = float(vector_score) + self.settings.lexical_weight * lexical_score
            matches.append(
                RagMatch(
                    index=index,
                    combined_score=combined_score,
                    vector_score=float(vector_score),
                    lexical_score=lexical_score,
                    record=record,
                    chunk=chunk,
                    parent_section=None,
                    evidence_type="code",
                )
            )

        matches.sort(key=lambda match: match.combined_score, reverse=True)
        return matches[: top_k or self.settings.code_top_k]


def build_citations(matches: list[RagMatch]) -> list[Citation]:
    return [match.citation(rank) for rank, match in enumerate(matches, start=1)]


def build_context(matches: list[RagMatch], max_total_chars: int, rank_offset: int = 0) -> str:
    if not matches:
        return "未检索到可用片段。"

    pieces: list[str] = []
    remaining = max_total_chars
    for local_rank, match in enumerate(matches, start=1):
        if remaining <= 0:
            break
        piece = match.prompt_context(rank_offset + local_rank, max_chars=min(1600, remaining))
        pieces.append(piece)
        remaining -= len(piece)
    return "\n\n".join(pieces)


def build_split_context(
    manual_matches: list[RagMatch],
    code_matches: list[RagMatch],
    max_total_chars: int,
    code_focused: bool = False,
) -> str:
    if code_focused:
        code_budget = max(5200, int(max_total_chars * 0.78))
        manual_budget = max(1200, max_total_chars - code_budget)
        code_context = build_context(code_matches, code_budget, rank_offset=0)
        manual_context = build_context(manual_matches, manual_budget, rank_offset=len(code_matches))
        return "\n\n".join(
            [
                "## 项目处理代码证据 code",
                code_context,
                "## GAMMA 手册证据 manual",
                manual_context,
            ]
        )

    manual_budget = max(2500, int(max_total_chars * 0.58))
    code_budget = max(2200, max_total_chars - manual_budget)
    manual_context = build_context(manual_matches, manual_budget, rank_offset=0)
    code_context = build_context(code_matches, code_budget, rank_offset=len(manual_matches))
    return "\n\n".join(
        [
            "## GAMMA 手册证据 manual",
            manual_context,
            "## 项目处理代码证据 code",
            code_context,
        ]
    )
