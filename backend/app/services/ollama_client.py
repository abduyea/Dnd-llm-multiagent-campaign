from __future__ import annotations

import hashlib as _hashlib
import json as _json
import os as _os
import re as _re
from collections.abc import AsyncIterator
from typing import Any

import httpx

OLLAMA_BASE_URL = _os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_TIMEOUT = int(_os.getenv("OLLAMA_TIMEOUT", "8"))
TERTIARY_TIMEOUT = int(_os.getenv("OLLAMA_TERTIARY_TIMEOUT", "180"))

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_THINK_OPEN_LEN = len(_THINK_OPEN)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks emitted by qwen3 before the actual response."""
    return _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).lstrip()

_FALLBACK_MODELS: list[dict[str, Any]] = [
    {"name": "qwen3", "timeout": DEFAULT_TIMEOUT},
    {"name": "mistral-nemo", "timeout": DEFAULT_TIMEOUT},
    {"name": "llama3.2:3b", "timeout": max(DEFAULT_TIMEOUT, TERTIARY_TIMEOUT)},
]


def _call_ollama(
    model: str,
    prompt: str,
    system_prompt: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str | None:
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if system_prompt:
        payload["system"] = system_prompt

    try:
        with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            response_text: object = data.get("response", "")
            return _strip_think_tags(str(response_text)) if isinstance(response_text, str) else ""
    except (httpx.HTTPError, _json.JSONDecodeError, KeyError, OSError):
        return None


def is_ollama_available() -> bool:
    """Return True if Ollama is reachable (quick connectivity check, no model load)."""
    try:
        with httpx.Client(timeout=httpx.Timeout(2.0)) as client:
            resp = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            return resp.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def generate(
    prompt: str,
    system_prompt: str | None = None,
    action_text: str = "the action",
) -> str:
    """Try each model in the fallback chain; return static narration if all fail."""
    for model_info in _FALLBACK_MODELS:
        result = _call_ollama(
            model=model_info["name"],
            prompt=prompt,
            system_prompt=system_prompt,
            timeout=model_info["timeout"],
        )
        if result:
            return result
    return _static_fallback(action_text)


_STATIC_NARRATIONS = [
    (
        "The air around you thickens as you move with purpose. "
        "Your action sends a ripple through the moment — something shifts in "
        "the unseen fabric of the world, though its consequence remains veiled for now.\n\n"
        "The others nearby sense the change, their eyes tracking you with a mixture "
        "of wariness and curiosity. Whatever comes next, you have set it in motion."
    ),
    (
        "Dust motes drift in the torchlight as your intent crystallises into deed. "
        "The ancient stones of this place have borne witness to a thousand such moments "
        "and will carry the memory of this one forward into the dark.\n\n"
        "A heartbeat of silence follows — then the world resumes its rhythm, "
        "altered in ways both subtle and profound."
    ),
    (
        "Your action cuts through the tension like a blade. "
        "Every eye in the vicinity — seen and unseen — turns toward you as the "
        "moment resolves itself into consequence.\n\n"
        "The dungeon breathes around you. Whatever you sought, you have taken a "
        "step toward it — or away from it. Only time will tell which."
    ),
    (
        "The weight of the moment presses down as you act. "
        "Stone and shadow bear silent witness, indifferent to courage or folly alike.\n\n"
        "A sound — distant, sourceless — echoes once and fades. "
        "Something has changed in this place, though you cannot yet name what."
    ),
    (
        "Fortune is a fickle ally, and she watches with cold amusement. "
        "Your action reverberates through the chamber — or the street, or the hall — "
        "and the world leans in to see what follows.\n\n"
        "The dice have spoken. The story continues."
    ),
]


async def generate_stream(
    prompt: str,
    system_prompt: str | None = None,
    action_text: str = "the action",
) -> AsyncIterator[str]:
    """Stream narration tokens from Ollama; yields static text word-by-word if all models fail."""
    for model_info in _FALLBACK_MODELS:
        payload: dict[str, Any] = {
            "model": model_info["name"],
            "prompt": prompt,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt
        yielded = False
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(model_info["timeout"])) as client:
                async with client.stream(
                    "POST", f"{OLLAMA_BASE_URL}/api/generate", json=payload
                ) as resp:
                    resp.raise_for_status()
                    # State for buffered <think> stripping (qwen3 reasoning blocks)
                    buf = ""
                    past_think_check = False
                    suppressing = False
                    async for raw_line in resp.aiter_lines():
                        if not raw_line:
                            continue
                        try:
                            data = _json.loads(raw_line)
                        except _json.JSONDecodeError:
                            continue
                        token: str = data.get("response", "")
                        if token:
                            if not past_think_check:
                                buf += token
                                if _THINK_CLOSE in buf:
                                    # Both open+close in buffer — yield post-think content
                                    past_think_check = True
                                    after = buf.split(_THINK_CLOSE, 1)[1].lstrip()
                                    buf = ""
                                    if after:
                                        yielded = True
                                        yield after
                                elif _THINK_OPEN in buf:
                                    # Opening tag seen — suppress until close tag
                                    past_think_check = True
                                    suppressing = True
                                elif not buf.startswith("<") or len(buf) >= _THINK_OPEN_LEN:
                                    # No think block — flush buffer and yield directly
                                    past_think_check = True
                                    if buf:
                                        yielded = True
                                        yield buf
                                        buf = ""
                            elif suppressing:
                                buf += token
                                if _THINK_CLOSE in buf:
                                    after = buf.split(_THINK_CLOSE, 1)[1].lstrip()
                                    suppressing = False
                                    buf = ""
                                    if after:
                                        yielded = True
                                        yield after
                            else:
                                yielded = True
                                yield token
                        if data.get("done"):
                            # Flush any buffered content on stream end
                            if not past_think_check or suppressing:
                                clean = _strip_think_tags(buf).lstrip()
                                if clean:
                                    yield clean
                            return
        except (httpx.HTTPError, OSError):
            pass
        if yielded:
            return
    for word in _static_fallback(action_text).split(" "):
        if word:
            yield word + " "


def _static_fallback(action_text: str) -> str:
    idx = int(_hashlib.md5(action_text.encode(), usedforsecurity=False).hexdigest(), 16) % len(
        _STATIC_NARRATIONS
    )
    return _STATIC_NARRATIONS[idx]
