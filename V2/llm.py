"""
Thin Ollama wrapper.

Single synchronous `chat(messages, model)` call. Returns a `ChatResult`
that carries both the cleaned text (fed to `tags.py`) and the raw
completion (kept in measurement logs for M3 to re-tune prompts against
actual failures).

qwen3 emits `<think>...</think>` reasoning blocks by default; they are
stripped here so downstream tag extraction sees only the model's final
output. The raw completion preserves them for postmortem analysis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import ollama


DEFAULT_MODEL = "qwen3:14b"

_THINK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ChatResult:
    text: str  # post-<think>-strip, what tags.py sees
    raw: str  # original model output, including <think>
    model: str
    prompt_chars: int
    completion_chars: int  # chars in `raw`
    latency_s: float


def chat(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    options: dict[str, Any] | None = None,
) -> ChatResult:
    """
    Send `messages` (a list of {role, content} dicts) to Ollama and return
    the result with timing + size measurements.

    Raises whatever the `ollama` client raises on network / server errors.
    Callers (M2 runner) treat any exception as a hard turn-abort; M3 will
    add retry around this.
    """
    prompt_chars = sum(len(m.get("content", "")) for m in messages)

    start = perf_counter()
    response = ollama.chat(
        model=model,
        messages=messages,
        stream=False,
        options=options or {},
    )
    latency = perf_counter() - start

    raw = _extract_content(response)
    text = _strip_thinking(raw).strip()

    return ChatResult(
        text=text,
        raw=raw,
        model=model,
        prompt_chars=prompt_chars,
        completion_chars=len(raw),
        latency_s=latency,
    )


def _strip_thinking(text: str) -> str:
    """Remove qwen3-style `<think>...</think>` blocks."""
    return _THINK_RE.sub("", text)


def _extract_content(response: Any) -> str:
    """Pull the message content from an ollama response (handles both
    attribute-style and dict-style returns across client versions)."""
    try:
        return response.message.content
    except AttributeError:
        return response["message"]["content"]
