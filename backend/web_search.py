from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable

from .config import BackendSettings
from .query_planner import QueryPlan
from .schemas import Citation, QueryType


EXPLICIT_WEB_SEARCH_PATTERN = re.compile(
    r"联网|网页|网上|搜索|查一下|查找|最新|近年|recent|latest|web|internet|online",
    re.IGNORECASE,
)
TRUSTED_DOMAIN_HINTS = (
    ".gov",
    ".edu",
    ".ac.",
    "esa.int",
    "nasa.gov",
    "jpl.nasa.gov",
    "asf.alaska.edu",
    "gfz-potsdam.de",
    "dlr.de",
    "usgs.gov",
    "unavco.org",
    "earthdata.nasa.gov",
    "eo-college.org",
    "carleton.ca",
)
LOW_TRUST_DOMAIN_HINTS = (
    "blog.csdn.net",
    "zhihu.com",
    "baijiahao.baidu.com",
    "blogspot.",
)


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str
    score: float

    def citation(self, rank: int) -> Citation:
        return Citation(
            id=f"web-{rank:02d}",
            source=self.title or "Web search result",
            page=self.url or "web",
            command_name="N/A",
            section="网页搜索补充",
            verification_status="web_reference",
            retrieval_score=round(self.score, 4),
            excerpt=_compact_text(self.snippet, 650),
        )

    def prompt_context(self, rank: int, max_chars: int) -> str:
        return "\n".join(
            [
                f"[W{rank}]",
                "evidence_type: web",
                f"source: {self.title or 'Web search result'}",
                f"url: {self.url or 'N/A'}",
                f"score: {self.score:.4f}",
                "excerpt:",
                _compact_text(self.snippet, max_chars),
            ]
        )


class DuckDuckGoLiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._mode: str | None = None
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        css_class = attrs_dict.get("class", "")
        if tag == "a" and "result-link" in css_class:
            self._finish_current()
            self._current = {"url": _decode_duckduckgo_url(attrs_dict.get("href", ""))}
            self._title_parts = []
            self._snippet_parts = []
            self._mode = "title"
            return
        if tag == "td" and "result-snippet" in css_class and self._current is not None:
            self._mode = "snippet"

    def handle_data(self, data: str) -> None:
        if self._mode == "title":
            self._title_parts.append(data)
        elif self._mode == "snippet":
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._mode == "title":
            self._mode = None
        elif tag == "td" and self._mode == "snippet":
            self._mode = None

    def close(self) -> None:
        super().close()
        self._finish_current()

    def _finish_current(self) -> None:
        if not self._current:
            return
        title = _clean_html_text(" ".join(self._title_parts))
        snippet = _clean_html_text(" ".join(self._snippet_parts))
        url = self._current.get("url", "")
        if title and url:
            self.results.append({"title": title, "url": url, "snippet": snippet})
        self._current = None
        self._title_parts = []
        self._snippet_parts = []
        self._mode = None


class WebSearchClient:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings

    def search(self, query: str, max_results: int | None = None) -> list[WebSearchResult]:
        if not self.settings.web_search_enabled:
            return []
        if self.settings.web_search_provider.lower() in {"", "disabled", "off", "none"}:
            return []
        if self.settings.web_search_provider.lower() != "duckduckgo_lite":
            raise RuntimeError(f"Unsupported WEB_SEARCH_PROVIDER: {self.settings.web_search_provider}")
        return self._search_duckduckgo_lite(query, max_results or self.settings.web_search_max_results)

    def _search_duckduckgo_lite(self, query: str, max_results: int) -> list[WebSearchResult]:
        params = urllib.parse.urlencode({"q": query})
        url = f"https://lite.duckduckgo.com/lite/?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=self.settings.web_search_timeout_seconds) as response:
                html_text = response.read().decode("utf-8", errors="replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return []

        parser = DuckDuckGoLiteParser()
        parser.feed(html_text)
        parser.close()

        candidates: list[WebSearchResult] = []
        for index, item in enumerate(parser.results[: max_results * 4], start=1):
            candidates.append(
                WebSearchResult(
                    title=item["title"],
                    url=item["url"],
                    snippet=item.get("snippet", ""),
                    score=max(0.0, 1.0 - (index - 1) * 0.08 + _domain_boost(item["url"])),
                )
            )
        candidates.sort(key=lambda result: result.score, reverse=True)
        return candidates[:max_results]


def should_use_web_search(
    settings: BackendSettings,
    question: str,
    query_types: list[QueryType],
    plan: QueryPlan,
    local_matches: Iterable[object],
) -> bool:
    if not settings.web_search_enabled:
        return False
    if settings.web_search_provider.lower() in {"", "disabled", "off", "none"}:
        return False
    if EXPLICIT_WEB_SEARCH_PATTERN.search(question):
        return True
    if plan.answer_mode in {"manual_command", "project_code_wrapper", "internal_workflow"}:
        return False
    if "command" in query_types or "parameter" in query_types:
        return False

    matches = list(local_matches)
    if not matches:
        return True

    best_score = max(float(getattr(match, "combined_score", 0.0)) for match in matches)
    best_vector = max(float(getattr(match, "vector_score", 0.0)) for match in matches)
    has_lexical_anchor = any(float(getattr(match, "lexical_score", 0.0)) >= 0.25 for match in matches[:4])

    if plan.answer_mode in {"concept", "manual_guidance"}:
        return best_score < settings.web_search_min_score or (not has_lexical_anchor and best_vector < 0.52)
    return False


def build_web_search_query(question: str, query_types: list[QueryType], plan: QueryPlan) -> str:
    suffixes: list[str] = []
    if plan.answer_mode == "concept" or "concept" in query_types:
        suffixes.append("SAR InSAR remote sensing concept ESA NASA ASF GFZ")
    if "workflow" in query_types:
        suffixes.append("SAR InSAR tutorial processing workflow")
    if "最新" in question or "近年" in question:
        suffixes.append("recent research")
    return _compact_text(" ".join([question, *suffixes]), 300)


def build_web_context(results: list[WebSearchResult], max_total_chars: int = 2200) -> str:
    if not results:
        return ""
    pieces: list[str] = ["## 网页搜索补充证据 web"]
    remaining = max_total_chars
    for rank, result in enumerate(results, start=1):
        if remaining <= 0:
            break
        piece = result.prompt_context(rank, max_chars=min(700, remaining))
        pieces.append(piece)
        remaining -= len(piece)
    return "\n\n".join(pieces)


def build_web_citations(results: list[WebSearchResult]) -> list[Citation]:
    return [result.citation(rank) for rank, result in enumerate(results, start=1)]


def _decode_duckduckgo_url(href: str) -> str:
    if href.startswith("//"):
        href = f"https:{href}"
    parsed = urllib.parse.urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return target
    return href


def _clean_html_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _domain_boost(url: str) -> float:
    domain = urllib.parse.urlparse(url).netloc.lower()
    if any(hint in domain for hint in TRUSTED_DOMAIN_HINTS):
        return 0.32
    if any(hint in domain for hint in LOW_TRUST_DOMAIN_HINTS):
        return -0.28
    if domain.endswith(".org"):
        return 0.08
    return 0.0


def _compact_text(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 16]}... [已截断]"
