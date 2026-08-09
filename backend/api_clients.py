from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

import numpy as np

from .config import BackendSettings
from .schemas import ChatTurn


def _join_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{base_url.rstrip('/')}{normalized_path}"


def _post_json_with_retries(
    url: str,
    payload: dict[str, Any],
    api_key: str,
    timeout: int,
    max_retries: int = 4,
) -> dict[str, Any]:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(max_retries + 1):
        request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {429, 500, 502, 503, 504} and attempt < max_retries:
                time.sleep(min(2**attempt, 10))
                continue
            raise RuntimeError(f"HTTP {exc.code}: {body[:800]}") from exc
        except urllib.error.URLError as exc:
            if attempt < max_retries:
                time.sleep(min(2**attempt, 10))
                continue
            raise RuntimeError(str(exc)) from exc

    raise RuntimeError("request failed after retries")


def _normalize_vector(values: list[float]) -> np.ndarray:
    vector = np.array(values, dtype="float32")
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector /= norm
    return vector


class SiliconFlowEmbeddingClient:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings

    def embed_query(self, query: str) -> np.ndarray:
        if not self.settings.siliconflow_api_key:
            raise RuntimeError("Missing SILICONFLOW_API_KEY")

        payload = {
            "model": self.settings.siliconflow_embedding_model,
            "input": [query],
            "encoding_format": "float",
        }
        response = _post_json_with_retries(
            _join_url(self.settings.siliconflow_api_base_url, "/embeddings"),
            payload,
            self.settings.siliconflow_api_key,
            self.settings.request_timeout_seconds,
        )
        data = response.get("data")
        if not isinstance(data, list) or not data:
            raise RuntimeError(f"Unexpected SiliconFlow response: {str(response)[:500]}")
        embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
        if not isinstance(embedding, list):
            raise RuntimeError(f"Missing embedding in SiliconFlow response: {str(data[0])[:500]}")
        return _normalize_vector(embedding)


class DeepSeekChatClient:
    def __init__(self, settings: BackendSettings) -> None:
        self.settings = settings

    def complete(
        self,
        system_prompt: str,
        history: list[ChatTurn],
        user_prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        if not self.settings.deepseek_api_key:
            raise RuntimeError("Missing DEEPSEEK_API_KEY")

        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for turn in history[-6:]:
            messages.append({"role": turn.role, "content": turn.content})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.settings.deepseek_chat_model,
            "messages": messages,
            "temperature": self.settings.deepseek_temperature if temperature is None else temperature,
            "max_tokens": self.settings.deepseek_max_tokens if max_tokens is None else max_tokens,
        }
        response = _post_json_with_retries(
            _join_url(self.settings.deepseek_api_base_url, self.settings.deepseek_api_path),
            payload,
            self.settings.deepseek_api_key,
            self.settings.request_timeout_seconds,
        )
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError(f"Unexpected DeepSeek response: {str(response)[:800]}")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError(f"Missing content in DeepSeek response: {str(response)[:800]}")
        return content.strip()
