"""Async LLM client for general-mode PPT generation.

Uses OpenAI-compatible chat completions API. Reads credentials from:
1. User's default credential in the `credentials` table (if available)
2. Falls back to settings.openai_api_key / settings.openai_base_url
"""

from __future__ import annotations

import json
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
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    return _client


class LLMClient:
    """Thin async wrapper around OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.model = model or settings.llm_model

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 4000,
    ) -> str:
        """Send a chat completion request and return the assistant's text."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = await self._post(payload)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM returned empty choices: {data}")
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
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
        """Send a chat completion request with JSON mode and parse the response."""
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
        data = await self._post(payload)
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM returned empty choices: {data}")
        content = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        logger.info(
            "llm_complete_json",
            model=self.model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown fences
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                return json.loads(content[start:end].strip())
            if "```" in content:
                start = content.index("```") + 3
                end = content.index("```", start)
                return json.loads(content[start:end].strip())
            raise

    async def _post(self, payload: dict) -> dict:
        """POST to the chat completions endpoint."""
        client = _get_client()
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            body = resp.text[:500]
            logger.error("llm_api_error", status=resp.status_code, body=body)
            raise RuntimeError(f"LLM API error {resp.status_code}: {body}")
        return resp.json()

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
