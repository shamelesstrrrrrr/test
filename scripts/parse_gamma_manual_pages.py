from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader


DEFAULT_PDF_GLOB = "I:/23346-main/GAMMA*.pdf"
DEFAULT_OUTPUT_DIR = "knowledge/gamma/parsed"
DEFAULT_SLUG = "gamma_new_user_manual_cn_2019"


def normalize_page_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+$", "", line) for line in text.split("\n")]
    normalized = "\n".join(lines).strip()
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized


def safe_metadata(reader: PdfReader) -> dict[str, str]:
    metadata = reader.metadata or {}
    return {str(key): str(value) for key, value in metadata.items()}


def flatten_outline_items(items: list[Any], level: int = 0) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []

    for item in items:
        if isinstance(item, list):
            flattened.extend(flatten_outline_items(item, level + 1))
            continue

        title = getattr(item, "title", None)
        if title:
            flattened.append({"level": level, "title": str(title)})

    return flattened


def choose_input_pdf(explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        return path

    matches = list(Path("I:/23346-main").glob("GAMMA*.pdf"))
    if not matches:
        raise FileNotFoundError(f"No PDF matched {DEFAULT_PDF_GLOB}")
    return matches[0]


def parse_pdf_pages(pdf_path: Path, output_dir: Path, slug: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    pages_jsonl_path = output_dir / f"{slug}.pages.jsonl"
    full_text_path = output_dir / f"{slug}.full_text.txt"
    manifest_path = output_dir / f"{slug}.manifest.json"

    reader = PdfReader(str(pdf_path))
    metadata = safe_metadata(reader)

    try:
        outline = flatten_outline_items(reader.outline)
    except Exception:
        outline = []

    page_records: list[dict[str, Any]] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            raw_text = page.extract_text(x_tolerance=1.5, y_tolerance=3) or ""
            text = normalize_page_text(raw_text)
            record = {
                "source": pdf_path.name,
                "source_path": str(pdf_path),
                "document_slug": slug,
                "pdf_page": page_index + 1,
                "page": page_index + 1,
                "width": page.width,
                "height": page.height,
                "char_count": len(text),
                "word_like_count": len(re.findall(r"\S+", text)),
                "extraction_status": "ok" if text else "empty",
                "text": text,
            }
            page_records.append(record)

    with pages_jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in page_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    with full_text_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# {pdf_path.name}\n\n")
        handle.write("说明：以下文本按 PDF 物理页码抽取，尚未切块。\n\n")
        for record in page_records:
            handle.write(f"\n\n--- PDF_PAGE {record['pdf_page']} ---\n\n")
            handle.write(record["text"])
            handle.write("\n")

    char_counts = [record["char_count"] for record in page_records]
    empty_pages = [record["pdf_page"] for record in page_records if record["extraction_status"] == "empty"]
    manifest = {
        "source_pdf": str(pdf_path),
        "source_filename": pdf_path.name,
        "document_slug": slug,
        "parsed_at_utc": datetime.now(timezone.utc).isoformat(),
        "parser": {
            "primary": "pdfplumber",
            "secondary": "pypdf",
            "text_extraction": "page.extract_text(x_tolerance=1.5, y_tolerance=3)",
        },
        "pdf_metadata": metadata,
        "page_count": len(page_records),
        "total_char_count": sum(char_counts),
        "empty_page_count": len(empty_pages),
        "empty_pages": empty_pages,
        "min_page_char_count": min(char_counts) if char_counts else 0,
        "max_page_char_count": max(char_counts) if char_counts else 0,
        "outputs": {
            "pages_jsonl": str(pages_jsonl_path),
            "full_text": str(full_text_path),
            "manifest": str(manifest_path),
        },
        "outline_items": outline,
        "notes": [
            "This output is page-level text only; no chunking has been applied.",
            "Tables and command layouts may need manual or layout-aware review before final RAG chunking.",
            "The page field uses physical PDF page numbers, not printed page numbers inside each translated module.",
        ],
    }

    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract page-level text from the GAMMA Chinese user manual.")
    parser.add_argument("--pdf", help="Path to the input PDF. Defaults to the GAMMA PDF under I:/23346-main.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for parsed outputs.")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Stable document slug used in output filenames.")
    args = parser.parse_args()

    pdf_path = choose_input_pdf(args.pdf)
    manifest = parse_pdf_pages(pdf_path, Path(args.output_dir), args.slug)

    print(json.dumps({
        "page_count": manifest["page_count"],
        "total_char_count": manifest["total_char_count"],
        "empty_page_count": manifest["empty_page_count"],
        "outputs": manifest["outputs"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
