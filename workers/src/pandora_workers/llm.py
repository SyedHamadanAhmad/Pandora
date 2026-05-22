"""OpenRouter LLM client (OpenAI-compatible async API)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import AsyncOpenAI

DEFAULT_MODEL = "qwen/qwen3.6-plus"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


def llm_configured() -> bool:
    """True when OPENROUTER_API_KEY is set."""
    return bool(os.environ.get("OPENROUTER_API_KEY", "").strip())


def openrouter_configured() -> bool:
    """Alias for llm_configured."""
    return llm_configured()


def deepseek_configured() -> bool:
    """Deprecated: use openrouter_configured()."""
    return llm_configured()


def _client() -> AsyncOpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    base_url = (
        os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL
    )
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


def _default_model() -> str:
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def _extract_json(text: str) -> str:
    stripped = text.strip()
    match = _JSON_BLOCK_RE.search(stripped)
    if match:
        return match.group(1).strip()
    return stripped


async def complete_text(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> str:
    client = _client()
    response = await client.chat.completions.create(
        model=model or _default_model(),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        timeout=timeout,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("LLM returned empty content")
    return content


async def complete_json(
    system: str,
    user: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Call LLM and parse a JSON object; retry once on parse failure."""
    last_error: Exception | None = None
    for attempt in range(2):
        prompt_user = user
        if attempt == 1:
            prompt_user = (
                f"{user}\n\n"
                "Respond with a single valid JSON object only. No markdown fences or prose."
            )
        text = await complete_text(
            system,
            prompt_user,
            model=model,
            temperature=temperature,
            timeout=timeout,
        )
        try:
            parsed = json.loads(_extract_json(text))
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object, got {type(parsed).__name__}")
        return parsed
    raise RuntimeError("LLM response was not valid JSON") from last_error
