from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_CHUNKS_JSONL = "knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.chunks.jsonl"
DEFAULT_OUTPUT_DIR = "knowledge/gamma/index"
DEFAULT_HF_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_SILICONFLOW_MODEL = "BAAI/bge-m3"
DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SLUG = "gamma_new_user_manual_cn_2019"
DEFAULT_BATCH_SIZE = 16
DEFAULT_MAX_LENGTH = 512
DEFAULT_HASHING_DIMENSIONS = 4096
DEFAULT_API_MAX_CHARS = 8000
DEFAULT_API_TIMEOUT = 60

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def read_chunks(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def build_embedding_text(chunk: dict[str, Any]) -> str:
    heading_path = " > ".join(chunk.get("heading_path") or [])
    parts = [
        f"chunk_type: {chunk.get('chunk_type')}",
        f"module: {chunk.get('module')}",
        f"section: {chunk.get('section_number')} {chunk.get('section_title')}",
        f"heading_path: {heading_path}",
        f"pages: {chunk.get('page_start')}-{chunk.get('page_end')}",
    ]
    command_name = chunk.get("command_name")
    if command_name:
        parts.append(f"command_name: {command_name}")
    commands_detected = chunk.get("commands_detected") or []
    if commands_detected:
        parts.append(f"commands_detected: {', '.join(commands_detected[:30])}")
    relative_path = chunk.get("relative_path")
    if relative_path:
        parts.append(f"relative_path: {relative_path}")
    code_language = chunk.get("code_language")
    if code_language:
        parts.append(f"code_language: {code_language}")
    if chunk.get("line_start") is not None and chunk.get("line_end") is not None:
        parts.append(f"lines: {chunk.get('line_start')}-{chunk.get('line_end')}")
    parts.append("text:")
    parts.append(chunk.get("text") or "")
    return "\n".join(str(part) for part in parts if part is not None).strip()


def resolve_model_name(backend: str, model_name: str | None) -> str:
    if model_name:
        return model_name
    if backend == "siliconflow":
        return os.getenv("SILICONFLOW_EMBEDDING_MODEL") or DEFAULT_SILICONFLOW_MODEL
    return DEFAULT_HF_MODEL


def stable_feature_hash(text: str) -> int:
    import hashlib

    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little", signed=False)


def tokenize_for_hashing(text: str) -> list[str]:
    features: list[str] = []

    for token in re.findall(r"[A-Za-z][A-Za-z0-9_./-]*|\d+(?:\.\d+)?", text):
        normalized = token.lower()
        features.append(f"tok:{normalized}")
        if "_" in normalized:
            features.append(f"cmd:{normalized}")
        if "." in normalized:
            features.append(f"path:{normalized}")

    chinese = re.sub(r"[^\u4e00-\u9fff]", "", text)
    for size in (2, 3):
        if len(chinese) >= size:
            for index in range(len(chinese) - size + 1):
                features.append(f"zh{size}:{chinese[index:index + size]}")

    return features


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return (matrix / norms).astype("float32")


def encode_texts_hashing(texts: list[str], dimensions: int) -> np.ndarray:
    matrix = np.zeros((len(texts), dimensions), dtype="float32")
    for row, text in enumerate(texts):
        for feature in tokenize_for_hashing(text):
            hashed = stable_feature_hash(feature)
            column = hashed % dimensions
            sign = 1.0 if ((hashed >> 63) & 1) == 0 else -1.0
            matrix[row, column] += sign

        norm = np.linalg.norm(matrix[row])
        if norm > 0:
            matrix[row] /= norm
        if (row + 1) % 100 == 0 or row + 1 == len(texts):
            print(f"embedded hashing rows {row + 1}/{len(texts)}", flush=True)
    return matrix


def build_api_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/embeddings"):
        return normalized
    return f"{normalized}/embeddings"


def post_json_with_retries(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: int,
    max_retries: int = 4,
) -> dict[str, Any]:
    encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(url, data=encoded_payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504} and attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))
                continue
            raise RuntimeError(f"SiliconFlow embedding request failed: HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt < max_retries:
                time.sleep(min(2 ** attempt, 10))
                continue
            raise RuntimeError(f"SiliconFlow embedding request failed: {exc}") from exc

    raise RuntimeError("SiliconFlow embedding request failed after retries.")


def trim_text_for_api(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    head_chars = max_chars // 2
    tail_chars = max_chars - head_chars
    trimmed = f"{text[:head_chars]}\n...[truncated for embedding only]...\n{text[-tail_chars:]}"
    return trimmed, True


def encode_texts_siliconflow(
    texts: list[str],
    model_name: str,
    batch_size: int,
    api_key: str,
    base_url: str,
    timeout: int,
) -> np.ndarray:
    url = build_api_url(base_url)
    vectors: list[list[float]] = []
    total_batches = math.ceil(len(texts) / batch_size)

    for batch_no, start in enumerate(range(0, len(texts), batch_size), start=1):
        batch_texts = texts[start : start + batch_size]
        payload = {
            "model": model_name,
            "input": batch_texts,
            "encoding_format": "float",
        }
        response = post_json_with_retries(url, payload, api_key, timeout)
        data = response.get("data")
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected SiliconFlow response shape: {str(response)[:500]}")

        indexed_items = []
        for fallback_index, item in enumerate(data):
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(embedding, list):
                raise RuntimeError(f"Missing embedding in SiliconFlow response item: {str(item)[:300]}")
            indexed_items.append((int(item.get("index", fallback_index)), embedding))

        vectors.extend(embedding for _, embedding in sorted(indexed_items, key=lambda pair: pair[0]))
        print(f"embedded siliconflow batch {batch_no}/{total_batches}", flush=True)

    return normalize_rows(np.array(vectors, dtype="float32"))


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def cosine_search(query_vector: np.ndarray, matrix: np.ndarray, top_k: int) -> list[tuple[int, float]]:
    scores = matrix @ query_vector
    if top_k >= len(scores):
        indices = np.argsort(-scores)
    else:
        indices = np.argpartition(-scores, top_k)[:top_k]
        indices = indices[np.argsort(-scores[indices])]
    return [(int(index), float(scores[index])) for index in indices]


def load_hf_model(model_name: str, device: str | None):
    import torch
    from transformers import AutoModel, AutoTokenizer

    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.to(resolved_device)
    model.eval()
    return tokenizer, model, resolved_device


def mean_pool(last_hidden_state, attention_mask):
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = torch.sum(last_hidden_state * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def encode_texts_hf(
    texts: list[str],
    model_name: str,
    batch_size: int,
    device: str | None,
    max_length: int,
    show_progress: bool,
) -> tuple[np.ndarray, str]:
    import torch

    tokenizer, model, resolved_device = load_hf_model(model_name, device)
    vectors: list[np.ndarray] = []
    total_batches = math.ceil(len(texts) / batch_size)

    with torch.no_grad():
        for batch_no, start in enumerate(range(0, len(texts), batch_size), start=1):
            batch_texts = texts[start : start + batch_size]
            encoded = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            encoded = {key: value.to(resolved_device) for key, value in encoded.items()}
            output = model(**encoded)
            pooled = mean_pool(output.last_hidden_state, encoded["attention_mask"])
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors.append(pooled.cpu().numpy())
            if show_progress:
                print(f"embedded hf batch {batch_no}/{total_batches}", flush=True)

    return np.vstack(vectors).astype("float32"), resolved_device


def embed_chunks(
    chunks_path: Path,
    output_dir: Path,
    model_name: str | None,
    batch_size: int,
    slug: str,
    device: str | None,
    max_length: int,
    backend: str,
    dimensions: int,
    api_key: str | None,
    api_base_url: str,
    api_timeout: int,
    api_max_chars: int,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = read_chunks(chunks_path)
    embedding_texts = [build_embedding_text(chunk) for chunk in chunks]

    started = time.time()
    api_truncated_count = 0
    effective_model = resolve_model_name(backend, model_name)
    if backend == "hashing":
        embeddings = encode_texts_hashing(embedding_texts, dimensions)
        resolved_device = "cpu"
        api_base_url_for_manifest = None
    elif backend == "hf":
        embeddings, resolved_device = encode_texts_hf(
            embedding_texts,
            model_name=effective_model,
            batch_size=batch_size,
            device=device,
            max_length=max_length,
            show_progress=True,
        )
        api_base_url_for_manifest = None
    elif backend == "siliconflow":
        resolved_api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        if not resolved_api_key:
            raise RuntimeError("Missing SiliconFlow API key. Set SILICONFLOW_API_KEY or pass --api-key.")

        api_texts: list[str] = []
        for text in embedding_texts:
            trimmed, was_truncated = trim_text_for_api(text, api_max_chars)
            api_texts.append(trimmed)
            api_truncated_count += int(was_truncated)

        embeddings = encode_texts_siliconflow(
            api_texts,
            model_name=effective_model,
            batch_size=batch_size,
            api_key=resolved_api_key,
            base_url=api_base_url,
            timeout=api_timeout,
        )
        resolved_device = "siliconflow_api"
        api_base_url_for_manifest = api_base_url
    else:
        raise ValueError(f"Unknown backend: {backend}")

    if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
        raise RuntimeError(f"Unexpected embedding shape: {embeddings.shape}")

    embeddings_path = output_dir / f"{slug}.embeddings.npy"
    records_path = output_dir / f"{slug}.embedding_records.jsonl"
    manifest_path = output_dir / f"{slug}.embedding_manifest.json"

    np.save(embeddings_path, embeddings)

    records: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks):
        records.append(
            {
                "embedding_index": index,
                "chunk_id": chunk["chunk_id"],
                "chunk_type": chunk["chunk_type"],
                "section_id": chunk["section_id"],
                "command_name": chunk.get("command_name"),
                "module": chunk.get("module"),
                "section_title": chunk.get("section_title"),
                "heading_path": chunk.get("heading_path"),
                "pages": chunk.get("pages"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "commands_detected": chunk.get("commands_detected"),
                "code_language": chunk.get("code_language"),
                "relative_path": chunk.get("relative_path"),
                "file_path": chunk.get("file_path"),
                "line_start": chunk.get("line_start"),
                "line_end": chunk.get("line_end"),
                "text_char_count": len(chunk.get("text") or ""),
                "embedding_text_char_count": len(embedding_texts[index]),
            }
        )
    write_jsonl(records_path, records)

    elapsed = time.time() - started
    manifest = {
        "document_slug": slug,
        "source_chunks_jsonl": str(chunks_path),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "embedding_model": effective_model,
        "hf_model": effective_model if backend == "hf" else None,
        "embedding_dimension": int(embeddings.shape[1]),
        "embedding_count": int(embeddings.shape[0]),
        "normalized_embeddings": True,
        "dtype": str(embeddings.dtype),
        "batch_size": batch_size,
        "max_length": max_length if backend == "hf" else None,
        "embedding_backend": backend,
        "api_base_url": api_base_url_for_manifest,
        "api_max_chars": api_max_chars if backend == "siliconflow" else None,
        "api_truncated_text_count": api_truncated_count if backend == "siliconflow" else None,
        "device": resolved_device,
        "elapsed_seconds": round(elapsed, 3),
        "outputs": {
            "embeddings": str(embeddings_path),
            "records": str(records_path),
            "manifest": str(manifest_path),
        },
        "retrieval_note": "Use cosine similarity. Because embeddings are normalized, dot product equals cosine similarity.",
        "indexed_chunk_types": sorted({chunk["chunk_type"] for chunk in chunks}),
        "small_to_big_note": "Use embedding_records.chunk_id to load the matching chunk, then use section_id to fetch section_parent and sibling chunks.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def demo_search(
    output_dir: Path,
    slug: str,
    model_name: str | None,
    query: str,
    top_k: int,
    device: str | None,
    max_length: int,
    chunks_jsonl: Path,
    backend: str,
    dimensions: int,
    api_key: str | None,
    api_base_url: str,
    api_timeout: int,
) -> list[dict[str, Any]]:
    embeddings = np.load(output_dir / f"{slug}.embeddings.npy")
    records = [json.loads(line) for line in (output_dir / f"{slug}.embedding_records.jsonl").open(encoding="utf-8")]
    chunks_by_id = {
        chunk["chunk_id"]: chunk
        for chunk in read_chunks(chunks_jsonl)
    }
    effective_model = resolve_model_name(backend, model_name)
    if backend == "hashing":
        query_vectors = encode_texts_hashing([query], dimensions)
    elif backend == "hf":
        query_vectors, _ = encode_texts_hf(
            [query],
            model_name=effective_model,
            batch_size=1,
            device=device,
            max_length=max_length,
            show_progress=False,
        )
    elif backend == "siliconflow":
        resolved_api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        if not resolved_api_key:
            raise RuntimeError("Missing SiliconFlow API key. Set SILICONFLOW_API_KEY or pass --api-key.")
        query_vectors = encode_texts_siliconflow(
            [query],
            model_name=effective_model,
            batch_size=1,
            api_key=resolved_api_key,
            base_url=api_base_url,
            timeout=api_timeout,
        )
    else:
        raise ValueError(f"Unknown backend: {backend}")

    query_vector = query_vectors[0]
    results = []
    for index, score in cosine_search(query_vector, embeddings, top_k):
        record = records[index]
        chunk = chunks_by_id.get(record["chunk_id"], {})
        results.append(
            {
                "rank": len(results) + 1,
                "score": round(score, 4),
                "chunk_id": record["chunk_id"],
                "chunk_type": record["chunk_type"],
                "command_name": record.get("command_name"),
                "section": record.get("section_title"),
                "pages": record.get("pages"),
                "text_preview": " ".join((chunk.get("text") or "").split())[:220],
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed GAMMA manual chunks.")
    parser.add_argument("--chunks-jsonl", default=DEFAULT_CHUNKS_JSONL, help="Chunk JSONL to embed.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for embedding outputs.")
    parser.add_argument("--model", help="Embedding model name. Defaults depend on --backend.")
    parser.add_argument("--backend", choices=["hashing", "hf", "siliconflow"], default="hashing", help="Embedding backend.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Embedding batch size.")
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH, help="Tokenizer max sequence length for hf backend.")
    parser.add_argument("--dimensions", type=int, default=DEFAULT_HASHING_DIMENSIONS, help="Hashing backend dimensions.")
    parser.add_argument("--slug", default=DEFAULT_SLUG, help="Stable document slug.")
    parser.add_argument("--device", help="Optional device override for hf backend, e.g. cpu or cuda.")
    parser.add_argument("--api-key", help="SiliconFlow API key. Prefer SILICONFLOW_API_KEY environment variable.")
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("SILICONFLOW_API_BASE_URL") or DEFAULT_SILICONFLOW_BASE_URL,
        help="SiliconFlow API base URL or full /embeddings endpoint.",
    )
    parser.add_argument("--api-timeout", type=int, default=DEFAULT_API_TIMEOUT, help="SiliconFlow request timeout in seconds.")
    parser.add_argument(
        "--api-max-chars",
        type=int,
        default=DEFAULT_API_MAX_CHARS,
        help="Maximum characters per embedded text for API backends; use 0 to disable trimming.",
    )
    parser.add_argument("--demo-query", default="SLC_intf 生成干涉图", help="Query used for a quick retrieval check.")
    parser.add_argument("--top-k", type=int, default=5, help="Top K demo retrieval results.")
    parser.add_argument("--skip-demo", action="store_true", help="Skip demo retrieval after embedding.")
    args = parser.parse_args()

    manifest = embed_chunks(
        chunks_path=Path(args.chunks_jsonl),
        output_dir=Path(args.output_dir),
        model_name=args.model,
        batch_size=args.batch_size,
        slug=args.slug,
        device=args.device,
        max_length=args.max_length,
        backend=args.backend,
        dimensions=args.dimensions,
        api_key=args.api_key,
        api_base_url=args.api_base_url,
        api_timeout=args.api_timeout,
        api_max_chars=args.api_max_chars,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))

    if not args.skip_demo:
        results = demo_search(
            Path(args.output_dir),
            args.slug,
            args.model,
            args.demo_query,
            args.top_k,
            args.device,
            args.max_length,
            Path(args.chunks_jsonl),
            args.backend,
            args.dimensions,
            args.api_key,
            args.api_base_url,
            args.api_timeout,
        )
        print(json.dumps({"demo_query": args.demo_query, "top_k": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
