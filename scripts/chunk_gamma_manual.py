from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_PAGES_JSONL = "knowledge/gamma/parsed/gamma_new_user_manual_cn_2019.pages.jsonl"
DEFAULT_OUTPUT_DIR = "knowledge/gamma/chunks"
DEFAULT_SLUG = "gamma_new_user_manual_cn_2019"

MAX_DIRECT_SECTION_CHARS = 1200
TARGET_SEMANTIC_CHARS = 1000
SEMANTIC_OVERLAP_CHARS = 150
MAX_COMMAND_CONTEXT_LINES = 2

COMMAND_CONTEXT_RE = re.compile(r"(程序|命令|脚本|命令行|执行|运行|使用|采用|指令|本示例)")
COMMAND_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
FIRST_TOKEN_RE = re.compile(r"^(?P<token>[A-Za-z][A-Za-z0-9_]{2,})(?:\s+|$)")
FILE_EXT_RE = re.compile(
    r"\.(?:slc|rslc|par|off|mli|int|flt|cc|smcc|diff_par|dem|hgt|unw|ras|bmp|tab|raw|ldr|grd)\b",
    re.IGNORECASE,
)
FILE_TOKEN_RE = re.compile(r"^(?:[A-Z]+[0-9]*_(?:tab|par)|[A-Z]+_[A-Z]+_par|TOPS_par)$")
HEADING_RE = re.compile(
    r"^(?P<number>(?:[A-Z]\.)?\d+(?:\.\d+){0,5}|[A-Z]\.\d+(?:\.\d+){0,5})(?:[\.、])?\s+(?P<title>[^.。]{1,120})$"
)
MODULE_RE = re.compile(r"GAMMA\s+用户手册\s*\n《(?P<title>[^》]+)》")

TERM_BLACKLIST = {
    "SAR",
    "SLC",
    "RSLC",
    "MLI",
    "PRI",
    "DEM",
    "GAMMA",
    "ISP",
    "DIFF",
    "GEO",
    "MSP",
    "LAT",
    "IPTA",
    "DISP",
    "ESA",
    "ERS",
    "JERS",
    "ALOS",
    "ASAR",
    "TOPS",
    "Figure",
    "Table",
}

KNOWN_NO_UNDERSCORE_COMMANDS = {
    "adf",
    "geocode",
    "dismph",
    "rasmph",
    "disSLC",
    "rasSLC",
    "dispwr",
    "raspwr",
    "dis2SLC",
}


@dataclass
class LineRecord:
    text: str
    page: int
    line_no: int


@dataclass
class SectionRecord:
    section_id: str
    module: str
    section_number: str
    section_title: str
    level: int
    heading_path: list[str]
    lines: list[LineRecord] = field(default_factory=list)

    @property
    def text(self) -> str:
        return normalize_text("\n".join(line.text for line in self.lines))

    @property
    def pages(self) -> list[int]:
        return sorted({line.page for line in self.lines})


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def stable_hash(text: str, size: int = 10) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:size]


def read_pages(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def find_module_title(page_text: str) -> str | None:
    match = MODULE_RE.search(page_text)
    if match:
        return match.group("title").strip()
    return None


def is_toc_line(line: str) -> bool:
    return "..." in line or "……" in line or line.count(".") >= 8


def heading_level(number: str) -> int:
    parts = [part for part in number.split(".") if part]
    if parts and len(parts[0]) == 1 and parts[0].isalpha():
        return len(parts)
    return len(parts)


def detect_heading(line: str) -> tuple[str, str, int] | None:
    stripped = line.strip()
    if not stripped or len(stripped) > 140 or is_toc_line(stripped):
        return None
    if stripped.isdigit():
        return None
    match = HEADING_RE.match(stripped)
    if not match:
        return None
    number = match.group("number").rstrip(".")
    title = match.group("title").strip()
    if not title or title.isdigit():
        return None
    if FILE_EXT_RE.search(title):
        return None
    return number, title, heading_level(number)


def parse_sections(pages: list[dict[str, Any]], slug: str) -> list[SectionRecord]:
    sections: list[SectionRecord] = []
    current_module = "Front matter"
    path_stack: list[str] = []
    current: SectionRecord | None = None
    section_index = 0

    def start_section(module: str, number: str, title: str, level: int, path: list[str]) -> SectionRecord:
        nonlocal section_index
        section_index += 1
        return SectionRecord(
            section_id=f"{slug}_sec_{section_index:04d}",
            module=module,
            section_number=number,
            section_title=title,
            level=level,
            heading_path=path.copy(),
        )

    def close_current() -> None:
        nonlocal current
        if current and current.text:
            sections.append(current)
        current = None

    current = start_section(current_module, "front", "Front matter", 0, ["Front matter"])

    for page in pages:
        page_number = int(page["page"])
        page_text = page["text"]
        module_title = find_module_title(page_text)
        if module_title and module_title != current_module:
            close_current()
            current_module = module_title
            path_stack = [module_title]
            current = start_section(current_module, "module", module_title, 0, path_stack)

        for line_no, raw_line in enumerate(page_text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue

            heading = detect_heading(line)
            if heading:
                number, title, level = heading
                close_current()
                path_stack = path_stack[: max(1, level)] if path_stack else []
                while len(path_stack) < level:
                    path_stack.append("")
                path_stack = path_stack[: level - 1] + [f"{number} {title}"]
                current = start_section(current_module, number, title, level, path_stack)

            if current is None:
                current = start_section(current_module, "unassigned", "Unassigned", 0, [current_module])
            current.lines.append(LineRecord(text=line, page=page_number, line_no=line_no))

    close_current()
    return sections


def count_param_like_tokens(text: str) -> int:
    parts = text.split()
    if len(parts) <= 1:
        return 0
    return sum(1 for part in parts[1:] if FILE_EXT_RE.search(part) or re.search(r"^-?\d+(?:\.\d+)?$", part) or "." in part)


def command_line_score(lines: list[LineRecord], index: int) -> tuple[str | None, int, list[str]]:
    line = lines[index].text.strip()
    match = FIRST_TOKEN_RE.match(line)
    if not match:
        return None, 0, []

    token = match.group("token")
    if token in TERM_BLACKLIST or FILE_TOKEN_RE.match(token):
        return None, 0, []
    if "_" not in token and token not in KNOWN_NO_UNDERSCORE_COMMANDS:
        return None, 0, []

    evidence: list[str] = ["line_start"]
    score = 2

    if "_" in token:
        score += 3
        evidence.append("underscore_token")

    context_start = max(0, index - MAX_COMMAND_CONTEXT_LINES)
    previous_context = " ".join(lines[pos].text for pos in range(context_start, index))
    if COMMAND_CONTEXT_RE.search(previous_context):
        score += 3
        evidence.append("command_context_before")

    param_like_count = count_param_like_tokens(line)
    if param_like_count >= 2:
        score += 2
        evidence.append("parameter_like_tail")

    if FILE_EXT_RE.search(line):
        score += 2
        evidence.append("file_extension_arguments")

    if len(line.split()) >= 4:
        score += 1
        evidence.append("multi_argument_line")

    if "_" not in token and token not in KNOWN_NO_UNDERSCORE_COMMANDS:
        score -= 3
        evidence.append("no_underscore_not_whitelisted")

    return token, score, evidence


def is_continuation_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or detect_heading(stripped):
        return False
    if COMMAND_CONTEXT_RE.search(stripped):
        return False
    asciiish = len(re.findall(r"[A-Za-z0-9_.\\/\-]+", stripped))
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", stripped))
    return bool(FILE_EXT_RE.search(stripped) or (asciiish >= 3 and chinese_chars < 8))


def command_mention_score(section: SectionRecord, token: str, start: int, end: int) -> tuple[int, list[str]]:
    if FILE_TOKEN_RE.match(token):
        return 0, ["file_token_pattern"]

    text = section.text
    before_char = text[start - 1] if start > 0 else ""
    after_char = text[end] if end < len(text) else ""
    if before_char in "./\\" or after_char in "./\\":
        return 0, ["filename_context"]

    window = text[max(0, start - 60) : min(len(text), end + 80)]
    evidence = ["underscore_token"]
    score = 3
    if COMMAND_CONTEXT_RE.search(window):
        score += 3
        evidence.append("near_command_context")
    if FILE_EXT_RE.search(window):
        score += 1
        evidence.append("near_file_extension")
    return score, evidence


def extract_command_blocks(section: SectionRecord, slug: str, start_index: int) -> tuple[list[dict[str, Any]], int]:
    blocks: list[dict[str, Any]] = []
    seen_line_indices: set[int] = set()
    block_index = start_index
    lines = section.lines

    for index in range(len(lines)):
        if index in seen_line_indices:
            continue

        token, score, evidence = command_line_score(lines, index)
        if not token or score < 6:
            continue

        start = index
        if "command_context_before" in evidence:
            start = max(0, index - MAX_COMMAND_CONTEXT_LINES)
            while start < index and not COMMAND_CONTEXT_RE.search(lines[start].text):
                start += 1

        end = index
        while end + 1 < len(lines) and end - index < 4 and is_continuation_line(lines[end + 1].text):
            end += 1

        while end + 1 < len(lines) and end - index < 6:
            next_line = lines[end + 1].text
            if detect_heading(next_line) or command_line_score(lines, end + 1)[1] >= 6:
                break
            if re.search(r"(该程序|该命令|结果|生成|输出|输入|支持|用于)", next_line):
                end += 1
                continue
            break

        line_span = lines[start : end + 1]
        text = normalize_text("\n".join(line.text for line in line_span))
        block_index += 1
        block_id = f"{slug}_cmd_{block_index:04d}_{stable_hash(token + text, 8)}"
        pages = sorted({line.page for line in line_span})
        blocks.append(
            {
                "chunk_id": block_id,
                "chunk_type": "command_block",
                "document_slug": slug,
                "source": section.lines[0].text if False else "GAMMA软件新用户手册中文版-2019.pdf",
                "module": section.module,
                "section_id": section.section_id,
                "section_number": section.section_number,
                "section_title": section.section_title,
                "heading_path": section.heading_path,
                "pages": pages,
                "page_start": pages[0],
                "page_end": pages[-1],
                "command_name": token,
                "confidence_score": score,
                "evidence": evidence,
                "overlap_left_chars": 0,
                "overlap_right_chars": 0,
                "parent_expansion": {
                    "strategy": "small_to_big",
                    "parent_section_id": section.section_id,
                    "recommended_neighbors": 1,
                },
                "text": text,
            }
        )
        seen_line_indices.update(range(start, end + 1))

    # Add high-confidence command mentions that did not appear as command-line blocks.
    existing_commands = {block["command_name"] for block in blocks}
    for match in COMMAND_TOKEN_RE.finditer(section.text):
        token = match.group(0)
        if token in existing_commands or token in TERM_BLACKLIST:
            continue
        score, evidence = command_mention_score(section, token, match.start(), match.end())
        if score < 6:
            continue
        window_start = max(0, match.start() - 180)
        window_end = min(len(section.text), match.end() + 260)
        text = normalize_text(section.text[window_start:window_end])
        block_index += 1
        block_id = f"{slug}_cmd_{block_index:04d}_{stable_hash(token + text, 8)}"
        pages = section.pages
        blocks.append(
            {
                "chunk_id": block_id,
                "chunk_type": "command_block",
                "document_slug": slug,
                "source": "GAMMA软件新用户手册中文版-2019.pdf",
                "module": section.module,
                "section_id": section.section_id,
                "section_number": section.section_number,
                "section_title": section.section_title,
                "heading_path": section.heading_path,
                "pages": pages,
                "page_start": pages[0],
                "page_end": pages[-1],
                "command_name": token,
                "confidence_score": score,
                "evidence": evidence,
                "overlap_left_chars": 0,
                "overlap_right_chars": 0,
                "parent_expansion": {
                    "strategy": "small_to_big",
                    "parent_section_id": section.section_id,
                    "recommended_neighbors": 1,
                },
                "text": text,
            }
        )
        existing_commands.add(token)

    return blocks, block_index


def split_text_units(text: str) -> list[str]:
    rough_units = re.split(r"(?<=[。！？；])\s*|\n+", text)
    return [unit.strip() for unit in rough_units if unit.strip()]


def sliding_windows(text: str, target_chars: int, overlap_chars: int) -> list[tuple[str, int, int]]:
    windows: list[tuple[str, int, int]] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target_chars)
        windows.append((text[start:end].strip(), overlap_chars if start > 0 else 0, overlap_chars if end < len(text) else 0))
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)
    return windows


def make_semantic_blocks(section: SectionRecord, slug: str, start_index: int) -> tuple[list[dict[str, Any]], int]:
    text = section.text
    if not text:
        return [], start_index

    pages = section.pages
    block_index = start_index
    pieces: list[tuple[str, int, int]] = []

    if len(text) <= MAX_DIRECT_SECTION_CHARS:
        pieces = [(text, 0, 0)]
    else:
        current = ""
        current_overlap_left = 0
        for unit in split_text_units(text):
            if len(unit) > TARGET_SEMANTIC_CHARS:
                if current:
                    pieces.append((current.strip(), current_overlap_left, SEMANTIC_OVERLAP_CHARS))
                    current = ""
                    current_overlap_left = SEMANTIC_OVERLAP_CHARS
                pieces.extend(sliding_windows(unit, TARGET_SEMANTIC_CHARS, SEMANTIC_OVERLAP_CHARS))
                current_overlap_left = SEMANTIC_OVERLAP_CHARS
                continue

            if len(current) + len(unit) + 1 <= TARGET_SEMANTIC_CHARS:
                current = f"{current} {unit}".strip()
            else:
                pieces.append((current.strip(), current_overlap_left, SEMANTIC_OVERLAP_CHARS))
                overlap_text = current[-SEMANTIC_OVERLAP_CHARS:] if current else ""
                current = f"{overlap_text} {unit}".strip()
                current_overlap_left = SEMANTIC_OVERLAP_CHARS if overlap_text else 0
        if current:
            pieces.append((current.strip(), current_overlap_left, 0))

    blocks: list[dict[str, Any]] = []
    for text_piece, overlap_left, overlap_right in pieces:
        if not text_piece:
            continue
        block_index += 1
        chunk_type = "section_block" if len(section.text) <= MAX_DIRECT_SECTION_CHARS else "semantic_block"
        block_id = f"{slug}_blk_{block_index:04d}_{stable_hash(section.section_id + text_piece, 8)}"
        blocks.append(
            {
                "chunk_id": block_id,
                "chunk_type": chunk_type,
                "document_slug": slug,
                "source": "GAMMA软件新用户手册中文版-2019.pdf",
                "module": section.module,
                "section_id": section.section_id,
                "section_number": section.section_number,
                "section_title": section.section_title,
                "heading_path": section.heading_path,
                "pages": pages,
                "page_start": pages[0],
                "page_end": pages[-1],
                "command_name": None,
                "confidence_score": None,
                "evidence": ["section_hierarchy"],
                "overlap_left_chars": overlap_left,
                "overlap_right_chars": overlap_right,
                "parent_expansion": {
                    "strategy": "small_to_big",
                    "parent_section_id": section.section_id,
                    "recommended_neighbors": 1 if chunk_type == "semantic_block" else 0,
                },
                "text": text_piece,
            }
        )
    return blocks, block_index


def serialize_section(section: SectionRecord, child_ids: list[str], slug: str) -> dict[str, Any]:
    pages = section.pages
    return {
        "section_id": section.section_id,
        "chunk_type": "section_parent",
        "document_slug": slug,
        "source": "GAMMA软件新用户手册中文版-2019.pdf",
        "module": section.module,
        "section_number": section.section_number,
        "section_title": section.section_title,
        "level": section.level,
        "heading_path": section.heading_path,
        "pages": pages,
        "page_start": pages[0],
        "page_end": pages[-1],
        "char_count": len(section.text),
        "child_chunk_ids": child_ids,
        "retrieval_role": "parent_context",
        "text": section.text,
    }


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def build_command_candidates(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_command: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        if chunk["chunk_type"] == "command_block" and chunk["command_name"]:
            by_command[chunk["command_name"]].append(chunk)

    candidates: list[dict[str, Any]] = []
    for command_name, items in sorted(by_command.items()):
        evidence_counter = Counter(evidence for item in items for evidence in item["evidence"])
        pages = sorted({page for item in items for page in item["pages"]})
        candidates.append(
            {
                "command_name": command_name,
                "occurrence_count": len(items),
                "pages": pages,
                "max_confidence_score": max(item["confidence_score"] or 0 for item in items),
                "evidence_counts": dict(evidence_counter),
                "sample_chunk_ids": [item["chunk_id"] for item in items[:5]],
                "review_status": "pending",
            }
        )
    return sorted(candidates, key=lambda item: (-item["max_confidence_score"], item["command_name"]))


def chunk_manual(pages_jsonl: Path, output_dir: Path, slug: str) -> dict[str, Any]:
    pages = read_pages(pages_jsonl)
    sections = parse_sections(pages, slug)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_chunks: list[dict[str, Any]] = []
    section_child_ids: dict[str, list[str]] = defaultdict(list)
    command_index = 0
    block_index = 0

    for section in sections:
        command_blocks, command_index = extract_command_blocks(section, slug, command_index)
        semantic_blocks, block_index = make_semantic_blocks(section, slug, block_index)
        for chunk in command_blocks + semantic_blocks:
            section_child_ids[section.section_id].append(chunk["chunk_id"])
            all_chunks.append(chunk)

    section_records = [serialize_section(section, section_child_ids[section.section_id], slug) for section in sections]
    command_candidates = build_command_candidates(all_chunks)

    sections_path = output_dir / f"{slug}.sections.jsonl"
    chunks_path = output_dir / f"{slug}.chunks.jsonl"
    commands_path = output_dir / f"{slug}.command_candidates.jsonl"
    manifest_path = output_dir / f"{slug}.chunk_manifest.json"

    write_jsonl(sections_path, section_records)
    write_jsonl(chunks_path, all_chunks)
    write_jsonl(commands_path, command_candidates)

    chunk_type_counts = Counter(chunk["chunk_type"] for chunk in all_chunks)
    manifest = {
        "source_pages_jsonl": str(pages_jsonl),
        "document_slug": slug,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategy": "small_to_big_hierarchical_command_first",
        "settings": {
            "max_direct_section_chars": MAX_DIRECT_SECTION_CHARS,
            "target_semantic_chars": TARGET_SEMANTIC_CHARS,
            "semantic_overlap_chars": SEMANTIC_OVERLAP_CHARS,
            "command_detection": [
                "underscore token is high-confidence evidence",
                "line-start command shape",
                "nearby Chinese context words such as 程序/命令/命令行/本示例",
                "GAMMA-like file extension arguments",
            ],
        },
        "counts": {
            "pages": len(pages),
            "sections": len(section_records),
            "chunks": len(all_chunks),
            "command_candidates": len(command_candidates),
            "chunk_types": dict(chunk_type_counts),
        },
        "outputs": {
            "sections": str(sections_path),
            "chunks": str(chunks_path),
            "command_candidates": str(commands_path),
            "manifest": str(manifest_path),
        },
        "notes": [
            "Section parents keep full section text for small-to-big expansion.",
            "Command blocks do not use overlap; they use parent_section_id and neighbor expansion.",
            "Semantic blocks use limited overlap only when a section exceeds the direct section threshold.",
            "Command candidates are not final authority; review_status remains pending for human validation.",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk parsed GAMMA manual pages with a command-first hierarchy.")
    parser.add_argument("--pages-jsonl", default=DEFAULT_PAGES_JSONL, help="Page-level JSONL created by parser.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for chunks.")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Stable document slug.")
    args = parser.parse_args()

    manifest = chunk_manual(Path(args.pages_jsonl), Path(args.output_dir), args.slug)
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))
    print(json.dumps(manifest["outputs"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
