from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


DEFAULT_CODE_ROOT = "处理代码/version2.0.2"
DEFAULT_OUTPUT_DIR = "knowledge/code/processing"
DEFAULT_SLUG = "processing_code_v2_0_2"
DEFAULT_MANUAL_COMMAND_CANDIDATES = "knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.command_candidates.jsonl"
DEFAULT_MAX_CHARS = 4500
DEFAULT_OVERLAP_LINES = 20
DEFAULT_MAX_FILE_BYTES = 2_000_000

TEXT_EXTENSIONS = {
    "",
    ".bash",
    ".c",
    ".cfg",
    ".conf",
    ".cpp",
    ".h",
    ".html",
    ".ini",
    ".json",
    ".m",
    ".md",
    ".pl",
    ".py",
    ".r",
    ".sh",
    ".txt",
    ".xml",
}

DOCX_EXTENSIONS = {".docx"}

SKIP_EXTENSIONS = {
    ".bmp",
    ".bolt",
    ".cm",
    ".dat",
    ".fig",
    ".gif",
    ".gain",
    ".jpg",
    ".mat",
    ".mlx",
    ".mltbx",
    ".mp4",
    ".npy",
    ".par",
    ".pdf",
    ".png",
    ".pyc",
    ".tif",
    ".zip",
}

SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".svn",
    "html",
    "helpsearch-v4_en",
}

KNOWN_GAMMA_COMMANDS = {
    "adf",
    "base_calc",
    "base_init",
    "base_perp",
    "base_plot",
    "create_diff_par",
    "create_offset",
    "create_offset_SLC",
    "create_dem_par",
    "dem_import",
    "dis2cc",
    "dis2pwr",
    "discc",
    "dismph",
    "dispwr",
    "geocode",
    "geocode_back",
    "gc_map",
    "gc_map_fine",
    "init_offset",
    "init_offset_orbit",
    "init_offset_orbitm",
    "init_offsetm",
    "mk_diff_2d",
    "multi_look",
    "multi_S1_TOPS",
    "offset_fit",
    "offset_fitm",
    "offset_pwr",
    "offset_pwrm",
    "rascc",
    "rasmph",
    "raspwr",
    "rdc_trans",
    "S1_OPOD_vec",
    "SLC_cat_S1_TOPS",
    "SLC_copy",
    "SLC_diff_intf",
    "SLC_interp",
    "SLC_interp_lt",
    "SLC_interp_lt_S1_TOPS",
    "SLC_intf",
    "SLC_mosaic_S1_TOPS",
    "SLC_tab",
    "SLC_to_SLC_par",
    "ScanSAR_burst_overlap",
    "ScanSAR_coreg.py",
    "ScanSAR_coreg_check.py",
}


def stable_id(*parts: str) -> str:
    digest = hashlib.blake2b("::".join(parts).encode("utf-8"), digest_size=6).hexdigest()
    return digest


def load_known_commands(path: Path | None) -> set[str]:
    commands = set(KNOWN_GAMMA_COMMANDS)
    if path and path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                command_name = record.get("command_name")
                if isinstance(command_name, str) and command_name:
                    commands.add(command_name)
    return commands


def decode_text_file(path: Path) -> tuple[str, str] | None:
    data = path.read_bytes()
    if b"\x00" in data[:4096]:
        return None
    for encoding in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None


def read_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        with archive.open("word/document.xml") as handle:
            tree = ElementTree.parse(handle)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in tree.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def should_include(path: Path, root: Path, max_file_bytes: int) -> bool:
    relative_parts = path.relative_to(root).parts
    if any(part in SKIP_DIR_NAMES for part in relative_parts):
        return False
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return False
    if path.stat().st_size > max_file_bytes and path.suffix.lower() not in DOCX_EXTENSIONS:
        return False
    return path.suffix.lower() in TEXT_EXTENSIONS or path.suffix.lower() in DOCX_EXTENSIONS


def detect_language(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return "python"
    if suffix == ".m":
        return "matlab"
    if suffix in {".bash", ".sh"} or suffix == "":
        return "shell"
    if suffix == ".docx":
        return "docx"
    if suffix in {".md", ".txt"}:
        return "markdown"
    if suffix in {".html", ".xml"}:
        return "markup"
    return suffix.lstrip(".") or "text"


def extract_gamma_commands(text: str, known_commands: set[str]) -> list[str]:
    candidates = set()
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.-]*\b", text):
        stripped = token.strip("./")
        if stripped in known_commands:
            candidates.add(stripped)
    return sorted(candidates)


def function_ranges(lines: list[str], language: str) -> list[tuple[int, int, str]]:
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines, start=1):
        if language == "python":
            match = re.match(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        elif language == "matlab":
            match = re.match(r"^\s*function(?:\s+\[[^\]]+\]|\s+[A-Za-z0-9_]+)?\s*=\s*([A-Za-z_][A-Za-z0-9_]*)|^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)", line)
        else:
            match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{", line)
        if match:
            name = next(group for group in match.groups() if group)
            starts.append((index, name))

    ranges: list[tuple[int, int, str]] = []
    for pos, (start, name) in enumerate(starts):
        end = starts[pos + 1][0] - 1 if pos + 1 < len(starts) else len(lines)
        ranges.append((start, end, name))
    return ranges


def split_line_window(
    lines: list[str],
    max_chars: int,
    overlap_lines: int,
    section_name: str,
) -> list[tuple[int, int, str]]:
    chunks: list[tuple[int, int, str]] = []
    start = 1
    while start <= len(lines):
        char_count = 0
        end = start
        while end <= len(lines):
            char_count += len(lines[end - 1]) + 1
            if char_count >= max_chars and end > start:
                break
            end += 1
        end = min(end, len(lines))
        chunks.append((start, end, section_name))
        if end == len(lines):
            break
        start = max(end - overlap_lines + 1, start + 1)
    return chunks


def chunk_text(
    text: str,
    language: str,
    max_chars: int,
    overlap_lines: int,
) -> list[tuple[int, int, str, str]]:
    lines = text.splitlines()
    if not lines:
        return []

    ranges = function_ranges(lines, language)
    if not ranges:
        ranges = [(1, len(lines), "file")]

    chunks: list[tuple[int, int, str, str]] = []
    for start, end, name in ranges:
        block_lines = lines[start - 1 : end]
        block_text = "\n".join(block_lines).strip()
        if not block_text:
            continue
        if len(block_text) <= max_chars:
            chunks.append((start, end, name, block_text))
            continue

        for sub_start, sub_end, sub_name in split_line_window(block_lines, max_chars, overlap_lines, name):
            actual_start = start + sub_start - 1
            actual_end = start + sub_end - 1
            sub_text = "\n".join(lines[actual_start - 1 : actual_end]).strip()
            chunks.append((actual_start, actual_end, sub_name, sub_text))
    return chunks


def file_section_title(relative_path: str, symbol: str) -> str:
    path = Path(relative_path)
    if symbol and symbol != "file":
        return f"{path.name}::{symbol}"
    return path.name


def build_records(
    root: Path,
    slug: str,
    max_chars: int,
    overlap_lines: int,
    max_file_bytes: int,
    known_commands: set[str],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if not should_include(path, root, max_file_bytes):
            continue

        suffix = path.suffix.lower()
        language = detect_language(path)
        encoding = "docx"
        if suffix in DOCX_EXTENSIONS:
            try:
                text = read_docx_text(path)
            except Exception:
                continue
        else:
            decoded = decode_text_file(path)
            if decoded is None:
                continue
            text, encoding = decoded

        relative_path = path.relative_to(root).as_posix()
        module = relative_path.split("/", 1)[0] if "/" in relative_path else "root"
        heading_path = [part for part in Path(relative_path).parts]
        chunks = chunk_text(text, language, max_chars, overlap_lines)
        for chunk_no, (line_start, line_end, symbol, chunk_body) in enumerate(chunks, start=1):
            commands = extract_gamma_commands(chunk_body, known_commands)
            chunk_id = f"{slug}_code_{stable_id(relative_path, str(line_start), str(line_end), symbol)}"
            records.append(
                {
                    "chunk_id": chunk_id,
                    "chunk_type": "code_block" if language in {"python", "matlab", "shell"} else "code_doc_block",
                    "document_slug": slug,
                    "source": relative_path,
                    "module": module,
                    "section_id": f"{slug}_file_{stable_id(relative_path)}",
                    "section_number": f"L{line_start}-L{line_end}",
                    "section_title": file_section_title(relative_path, symbol),
                    "heading_path": heading_path,
                    "pages": [],
                    "page_start": None,
                    "page_end": None,
                    "command_name": commands[0] if len(commands) == 1 else None,
                    "commands_detected": commands,
                    "code_language": language,
                    "relative_path": relative_path,
                    "file_path": str(path),
                    "line_start": line_start,
                    "line_end": line_end,
                    "encoding": encoding,
                    "chunk_no": chunk_no,
                    "text_char_count": len(chunk_body),
                    "text": chunk_body,
                }
            )
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_text_dump(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write("=" * 88 + "\n")
            handle.write(f"chunk_id: {record['chunk_id']}\n")
            handle.write(f"source: {record['source']}\n")
            handle.write(f"section_title: {record['section_title']}\n")
            handle.write(f"lines: {record['section_number']}\n")
            handle.write(f"language: {record['code_language']}\n")
            handle.write(f"chunk_type: {record['chunk_type']}\n")
            handle.write(f"commands_detected: {', '.join(record['commands_detected']) or 'N/A'}\n")
            handle.write(f"text_char_count: {record['text_char_count']}\n")
            handle.write("-" * 88 + "\n")
            handle.write(record["text"].rstrip())
            handle.write("\n\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chunk local SAR/GAMMA processing code for RAG retrieval.")
    parser.add_argument("--code-root", default=DEFAULT_CODE_ROOT)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--manual-command-candidates", default=DEFAULT_MANUAL_COMMAND_CANDIDATES)
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--overlap-lines", type=int, default=DEFAULT_OVERLAP_LINES)
    parser.add_argument("--max-file-bytes", type=int, default=DEFAULT_MAX_FILE_BYTES)
    args = parser.parse_args()

    root = Path(args.code_root).resolve()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    known_commands = load_known_commands(Path(args.manual_command_candidates) if args.manual_command_candidates else None)
    records = build_records(root, args.slug, args.max_chars, args.overlap_lines, args.max_file_bytes, known_commands)
    chunks_path = output_dir / f"{args.slug}.chunks.jsonl"
    text_dump_path = output_dir / f"{args.slug}.parsed_text.txt"
    manifest_path = output_dir / f"{args.slug}.chunk_manifest.json"
    write_jsonl(chunks_path, records)
    write_text_dump(text_dump_path, records)

    manifest = {
        "document_slug": args.slug,
        "source_code_root": str(root),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "chunk_count": len(records),
        "max_chars": args.max_chars,
        "overlap_lines": args.overlap_lines,
        "max_file_bytes": args.max_file_bytes,
        "manual_command_candidates": args.manual_command_candidates,
        "known_command_count": len(known_commands),
        "chunk_types": sorted({record["chunk_type"] for record in records}),
        "languages": sorted({record["code_language"] for record in records}),
        "modules": sorted({record["module"] for record in records}),
        "outputs": {
            "chunks": str(chunks_path),
            "parsed_text": str(text_dump_path),
            "manifest": str(manifest_path),
        },
        "note": "These chunks are code and workflow references. They are auxiliary evidence; GAMMA command syntax should still be verified against manual chunks.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
