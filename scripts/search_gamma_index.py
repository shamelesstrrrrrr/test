from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_CHUNKS_JSONL = "knowledge/gamma/chunks/gamma_new_user_manual_cn_2019.chunks.jsonl"
DEFAULT_INDEX_DIR = "knowledge/gamma/index"
DEFAULT_SLUG = "gamma_new_user_manual_cn_2019"
DEFAULT_SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_API_TIMEOUT = 60

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def cosine_search(query_vector: np.ndarray, matrix: np.ndarray, top_k: int) -> list[tuple[int, float]]:
    scores = matrix @ query_vector
    if top_k >= len(scores):
        indices = np.argsort(-scores)
    else:
        indices = np.argpartition(-scores, top_k)[:top_k]
        indices = indices[np.argsort(-scores[indices])]
    return [(int(index), float(scores[index])) for index in indices]


def extract_query_terms(query: str) -> tuple[set[str], list[str]]:
    ascii_terms = {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_./-]*|\d+(?:\.\d+)?", query)
    }
    chinese_phrases = [
        phrase
        for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query)
    ]
    return ascii_terms, chinese_phrases


def score_lexical_match(query: str, record: dict[str, Any], chunk: dict[str, Any]) -> float:
    ascii_terms, chinese_phrases = extract_query_terms(query)
    command_name = (record.get("command_name") or "").lower()
    section_title = (record.get("section_title") or "").lower()
    heading_path = " ".join(record.get("heading_path") or []).lower()
    text = (chunk.get("text") or "")
    lower_text = text.lower()

    score = 0.0
    for term in ascii_terms:
        if command_name:
            if term == command_name:
                score += 1.8
            elif term in command_name or command_name in term:
                score += 1.0
        if term in section_title or term in heading_path:
            score += 0.35
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


def hybrid_search(
    query: str,
    query_vector: np.ndarray,
    matrix: np.ndarray,
    records: list[dict[str, Any]],
    chunks_by_id: dict[str, dict[str, Any]],
    top_k: int,
    lexical_weight: float,
) -> list[tuple[int, float, float, float]]:
    vector_scores = matrix @ query_vector
    scored: list[tuple[int, float, float, float]] = []
    for index, vector_score in enumerate(vector_scores):
        record = records[index]
        lexical_score = score_lexical_match(query, record, chunks_by_id.get(record["chunk_id"], {}))
        combined_score = float(vector_score) + lexical_weight * lexical_score
        scored.append((index, combined_score, float(vector_score), lexical_score))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


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


def encode_query_hashing(query: str, dimensions: int) -> np.ndarray:
    vector = np.zeros(dimensions, dtype="float32")
    for feature in tokenize_for_hashing(query):
        hashed = stable_feature_hash(feature)
        column = hashed % dimensions
        sign = 1.0 if ((hashed >> 63) & 1) == 0 else -1.0
        vector[column] += sign
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector


def mean_pool(last_hidden_state, attention_mask):
    import torch

    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = torch.sum(last_hidden_state * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def encode_query_hf(model_name: str, query: str, device: str | None, max_length: int) -> np.ndarray:
    import torch
    from transformers import AutoModel, AutoTokenizer

    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.to(resolved_device)
    model.eval()
    with torch.no_grad():
        encoded = tokenizer([query], padding=True, truncation=True, max_length=max_length, return_tensors="pt")
        encoded = {key: value.to(resolved_device) for key, value in encoded.items()}
        output = model(**encoded)
        pooled = mean_pool(output.last_hidden_state, encoded["attention_mask"])
        pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
    return pooled.cpu().numpy()[0].astype("float32")


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


def encode_query_siliconflow(
    model_name: str,
    query: str,
    api_key: str,
    base_url: str,
    timeout: int,
) -> np.ndarray:
    payload = {
        "model": model_name,
        "input": [query],
        "encoding_format": "float",
    }
    response = post_json_with_retries(build_api_url(base_url), payload, api_key, timeout)
    data = response.get("data")
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"Unexpected SiliconFlow response shape: {str(response)[:500]}")
    embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(embedding, list):
        raise RuntimeError(f"Missing embedding in SiliconFlow response item: {str(data[0])[:300]}")
    vector = np.array(embedding, dtype="float32")
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector


def main() -> None:
    parser = argparse.ArgumentParser(description="Search the local GAMMA embedding index.")
    parser.add_argument("query", help="Chinese or English search query.")
    parser.add_argument("--index-dir", default=DEFAULT_INDEX_DIR)
    parser.add_argument("--chunks-jsonl", default=DEFAULT_CHUNKS_JSONL)
    parser.add_argument("--slug", default=DEFAULT_SLUG)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--device", help="Optional device override for hf backend, e.g. cpu or cuda.")
    parser.add_argument("--max-length", type=int, help="Tokenizer max sequence length. Defaults to manifest max_length or 512.")
    parser.add_argument("--api-key", help="SiliconFlow API key. Prefer SILICONFLOW_API_KEY environment variable.")
    parser.add_argument(
        "--api-base-url",
        default=os.getenv("SILICONFLOW_API_BASE_URL") or DEFAULT_SILICONFLOW_BASE_URL,
        help="SiliconFlow API base URL or full /embeddings endpoint.",
    )
    parser.add_argument("--api-timeout", type=int, default=DEFAULT_API_TIMEOUT, help="SiliconFlow request timeout in seconds.")
    parser.add_argument(
        "--lexical-weight",
        type=float,
        default=0.2,
        help="Keyword boost weight for command names and exact technical terms. Use 0 for vector-only search.",
    )
    args = parser.parse_args()

    index_dir = Path(args.index_dir)
    manifest = json.loads((index_dir / f"{args.slug}.embedding_manifest.json").read_text(encoding="utf-8"))
    embeddings = np.load(index_dir / f"{args.slug}.embeddings.npy")
    records = read_jsonl(index_dir / f"{args.slug}.embedding_records.jsonl")
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in read_jsonl(Path(args.chunks_jsonl))}

    backend = manifest.get("embedding_backend", "hf")
    if backend == "hashing":
        query_vector = encode_query_hashing(args.query, int(manifest["embedding_dimension"]))
    elif backend == "hf":
        max_length = args.max_length or int(manifest.get("max_length") or 512)
        query_vector = encode_query_hf(manifest.get("hf_model") or manifest["embedding_model"], args.query, args.device, max_length)
    elif backend == "siliconflow":
        api_key = args.api_key or os.getenv("SILICONFLOW_API_KEY")
        if not api_key:
            raise RuntimeError("Missing SiliconFlow API key. Set SILICONFLOW_API_KEY or pass --api-key.")
        query_vector = encode_query_siliconflow(
            manifest["embedding_model"],
            args.query,
            api_key=api_key,
            base_url=manifest.get("api_base_url") or args.api_base_url,
            timeout=args.api_timeout,
        )
    else:
        raise ValueError(f"Unknown embedding backend in manifest: {backend}")

    results = []
    matches = hybrid_search(
        args.query,
        query_vector,
        embeddings,
        records,
        chunks_by_id,
        args.top_k,
        args.lexical_weight,
    )
    for rank, (index, score, vector_score, lexical_score) in enumerate(matches, start=1):
        record = records[index]
        chunk = chunks_by_id[record["chunk_id"]]
        results.append(
            {
                "rank": rank,
                "score": round(score, 4),
                "vector_score": round(vector_score, 4),
                "lexical_score": round(lexical_score, 4),
                "chunk_id": record["chunk_id"],
                "chunk_type": record["chunk_type"],
                "command_name": record.get("command_name"),
                "section": record.get("section_title"),
                "pages": record.get("pages"),
                "section_id": record["section_id"],
                "text_preview": " ".join(chunk["text"].split())[:300],
            }
        )

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
