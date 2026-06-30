"""Async LLM client for general-mode PPT generation.

Uses OpenAI-compatible chat completions API. Reads credentials from:
1. User's default credential in the `credentials` table (if available)
2. Falls back to settings.openai_api_key / settings.openai_base_url

Built-in resilience (Constitution §I — production-grade agent):
    * Exponential-backoff retry for 429 / 5xx / network errors
    * Respect of ``Retry-After`` header from upstream
    * Per-call timeout derived from ``max_tokens`` (no more 120s blanket)
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import httpx

from src.core.config import settings
from src.core.observability import get_logger

logger = get_logger("generation.llm_client")

# Module-level client (reused across requests)
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=10.0))
    return _client


# Status codes that should be retried. 4xx other than 429 are
# permanent (bad request, auth, etc.) and MUST NOT retry.
_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class _TransientLLMError(Exception):
    """Internal marker — wraps a retryable upstream failure."""


def _compute_retry_after_seconds(resp: httpx.Response, attempt: int) -> float:
    """Read upstream ``Retry-After`` or fall back to exponential backoff."""
    ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    if ra:
        try:
            return max(0.5, float(ra))
        except ValueError:
            pass
    # Exponential: 1, 2, 4, 8s with ±20% jitter
    base = min(8.0, 2 ** (attempt - 1))
    return base * (0.8 + 0.4 * random.random())


async def _post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    max_retries: int,
) -> dict[str, Any]:
    """POST with exponential-backoff retry on transient failures.

    Raises ``_TransientLLMError`` if all retries are exhausted, or
    ``RuntimeError`` for permanent (non-retryable) HTTP errors.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(url, json=payload, headers=headers)
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last_exc = e
            logger.warning(
                "llm_transport_error",
                attempt=attempt,
                max_retries=max_retries,
                error=repr(e),
            )
            if attempt == max_retries:
                raise _TransientLLMError(
                    f"LLM transport error after {max_retries} attempts: {e!r}"
                ) from e
            await asyncio.sleep(_compute_retry_after_seconds(_FakeResp(attempt), attempt))
            continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code in _RETRYABLE_STATUS:
            last_exc = RuntimeError(f"LLM {resp.status_code}: {resp.text[:200]}")
            logger.warning(
                "llm_retryable_status",
                attempt=attempt,
                max_retries=max_retries,
                status=resp.status_code,
            )
            if attempt == max_retries:
                raise _TransientLLMError(
                    f"LLM {resp.status_code} persisted after {max_retries} attempts"
                ) from last_exc
            await asyncio.sleep(_compute_retry_after_seconds(resp, attempt))
            continue

        # Permanent error — surface immediately, no retry
        body = resp.text[:500]
        logger.error("llm_api_error", status=resp.status_code, body=body)
        raise RuntimeError(f"LLM API error {resp.status_code}: {body}")

    # Should not reach here, but be safe
    raise _TransientLLMError(
        f"LLM request exhausted {max_retries} retries (last: {last_exc!r})"
    )


class _FakeResp:
    """Tiny stub used for backoff calculation when no real response is available."""

    def __init__(self, attempt: int) -> None:
        self.headers: dict[str, str] = {}


class LLMClient:
    """Thin async wrapper around OpenAI-compatible chat completions API.

    Accumulates real LLM-reported token usage in ``self.last_usage_total``
    across all ``complete*`` calls. Tool layers (see
    ``src.agents.agent_tools._persist_rendered_slides``) read this
    attribute to bill ``GenerationTask.token_consumed`` accurately
    instead of relying on a fixed per-slide estimate.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.max_retries = max_retries or settings.llm_max_retries
        # Token accounting — set after every complete() / complete_json()
        # call. Tools drain this to persist usage on the task row.
        self.last_usage_total: int = 0

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        """Send a chat completion request and return the assistant's text.

        Side effect: ``self.last_usage_total`` is incremented by the
        total_tokens reported by the upstream API (0 if missing).
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await _post_with_retry(
            _get_client(),
            f"{self.base_url}/chat/completions",
            payload,
            self._headers(),
            self.max_retries,
        )
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM returned empty choices: {data}")
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        total = int(usage.get("total_tokens", 0) or 0)
        self.last_usage_total += total
        logger.info(
            "llm_complete",
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        return content

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """Send a chat completion request with JSON mode and parse the response.

        Returns the parsed JSON dict. The dict is augmented with a
        private ``__usage__`` key carrying ``{"prompt_tokens": int,
        "completion_tokens": int, "total_tokens": int}`` so the
        caller can bill real usage back to ``GenerationTask.token_consumed``
        instead of relying on a fixed estimate.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = await _post_with_retry(
            _get_client(),
            f"{self.base_url}/chat/completions",
            payload,
            self._headers(),
            self.max_retries,
        )
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM returned empty choices: {data}")
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        total = int(usage.get("total_tokens", 0) or 0)
        self.last_usage_total += total
        logger.info(
            "llm_complete_json",
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown fences
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                parsed = json.loads(content[start:end].strip())
            elif "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                parsed = json.loads(content[start:end].strip())
            else:
                raise
        # Attach usage for billing / observability. The key starts
        # with `__` to discourage the LLM from echoing it back
        # when the result is fed into the next prompt.
        parsed["__usage__"] = {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
            "total_tokens": int(usage.get("total_tokens", 0)),
        }
        return parsed

    async def complete_vision(
        self,
        system_prompt: str,
        user_text: str,
        image_bytes: bytes,
        image_mime: str = "image/jpeg",
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> str:
        """Multimodal chat completion. ``image_bytes`` is sent as a base64 data URL.

        Compatible with OpenAI / DashScope (qwen-vl-*) / OpenRouter endpoints
        that accept the OpenAI ``image_url`` content-block shape.
        """
        import base64

        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{image_mime};base64,{b64}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await _post_with_retry(
            _get_client(),
            f"{self.base_url}/chat/completions",
            payload,
            self._headers(),
            self.max_retries,
        )
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM returned empty choices: {data}")
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        logger.info(
            "llm_complete_vision",
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        return content

    async def complete_json_vision(
        self,
        system_prompt: str,
        user_text: str,
        image_bytes: bytes,
        image_mime: str = "image/jpeg",
        temperature: float = 0.1,
        max_tokens: int = 800,
    ) -> dict[str, Any]:
        """Vision + JSON response (best-effort). Falls back to text parsing on
        providers that don't honour ``response_format`` with images.
        """
        raw = await self.complete_vision(
            system_prompt=system_prompt,
            user_text=user_text,
            image_bytes=image_bytes,
            image_mime=image_mime,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            if "```json" in raw:
                start = raw.index("```json") + 7
                end = raw.index("```", start)
                return json.loads(raw[start:end].strip())
            if "```" in raw:
                start = raw.index("```") + 3
                end = raw.index("```", start)
                return json.loads(raw[start:end].strip())
            # Last-ditch: try to find the first {...} JSON object
            import re

            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group(0))
            raise

    @classmethod
    async def from_user_credential(cls, session: Any, user_id: str) -> LLMClient:
        """Create an LLMClient using the user's default credential."""
        from sqlalchemy import select

        from src.db.models import Credential

        result = await session.execute(
            select(Credential).where(
                Credential.owner_id == user_id,
                Credential.is_default.is_(True),
            )
        )
        cred = result.scalar_one_or_none()
        if not cred:
            # Fall back to settings
            return cls()

        cd = cred.credential_data
        api_key = cd.get("api_key") or cd.get("api_key_env") or settings.openai_api_key
        base_url = cd.get("base_url") or cd.get("api_base") or settings.openai_base_url
        model = cd.get("model") or settings.llm_model
        return cls(api_key=api_key, base_url=base_url, model=model)
