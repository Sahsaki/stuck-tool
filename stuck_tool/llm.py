"""
LLM abstraction layer using litellm for multi-provider support.

Supports OpenAI, Anthropic, Ollama, Azure, and 100+ other providers
through litellm's unified interface.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field

import litellm

logger = logging.getLogger("stuck_tool.llm")

# Suppress litellm's verbose logging by default
litellm.suppress_debug_info = True


@dataclass
class LLMConfig:
    """Configuration for the LLM provider."""

    model: str = ""
    api_key: str = field(default="", repr=False)
    api_base: str = ""
    max_concurrent: int = 10
    temperature: float = 0.9
    max_tokens: int = 8192
    timeout: int = 120
    retry_count: int = 2

    def __post_init__(self):
        if self.max_concurrent < 1 or self.max_tokens < 1 or self.timeout <= 0:
            raise ValueError("Concurrency, token limit, and timeout must be positive")
        if not 0 <= self.retry_count <= 2:
            raise ValueError("retry_count must be between 0 and 2")
        # Auto-detect model if not specified
        if not self.model:
            self.model = os.environ.get("STUCK_TOOL_MODEL", "")

        if not self.api_key:
            self.api_key = os.environ.get("STUCK_TOOL_API_KEY", "")

        if not self.api_base:
            self.api_base = os.environ.get("STUCK_TOOL_API_BASE", "")

        # Auto-detect model from available API keys
        if not self.model:
            self.model = self._detect_model()

    def _detect_model(self) -> str:
        """Try to detect the best available model from environment."""
        if os.environ.get("ANTHROPIC_API_KEY") or self.api_key:
            return "anthropic/claude-sonnet-4-20250514"
        if os.environ.get("OPENAI_API_KEY"):
            return "gpt-4o"
        if os.environ.get("OLLAMA_HOST") or self._ollama_available():
            return "ollama/llama3.1"
        # Default fallback
        return "anthropic/claude-sonnet-4-20250514"

    @staticmethod
    def _ollama_available() -> bool:
        """Check if Ollama is running locally."""
        try:
            import urllib.request

            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
            return True
        except Exception:
            return False


class LLMClient:
    """Async LLM client with concurrency control and retry logic."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent)
        self._total_calls = 0
        self._total_tokens = 0
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._requests = 0
        self._usage_missing_calls = 0

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str = "json",
    ) -> str:
        """
        Send a completion request to the LLM.

        Args:
            system_prompt: The system/instruction prompt.
            user_prompt: The user message.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.
            response_format: "json" to request JSON output, "text" for free text.

        Returns:
            The LLM's response text.
        """
        async with self._semaphore:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

            kwargs: dict = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature if temperature is None else temperature,
                "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
                "timeout": self.config.timeout,
                "num_retries": 0,  # This client owns the bounded retry policy.
            }

            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key

            if self.config.api_base:
                kwargs["api_base"] = self.config.api_base

            for attempt in range(self.config.retry_count + 1):
                try:
                    self._requests += 1
                    response = await litellm.acompletion(**kwargs)
                    break
                except Exception as e:
                    failure = type(e).__name__
                    transient = isinstance(
                        e,
                        (
                            litellm.RateLimitError,
                            litellm.Timeout,
                            litellm.APIConnectionError,
                        ),
                    ) or getattr(e, "status_code", 0) in {408, 429, 500, 502, 503, 504}
                    if transient and attempt < self.config.retry_count:
                        wait = 2**attempt
                        logger.warning("LLM request failed (%s), retrying in %ss", failure, wait)
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "LLM request failed (%s) after %s attempt(s)", failure, attempt + 1
                        )
                        # Provider exceptions can contain keys, URLs, and prompt text.
                        raise RuntimeError(
                            f"LLM request failed ({failure}). Check your provider settings. "
                            "Provider response details were omitted for privacy."
                        ) from None

            self._total_calls += 1
            if hasattr(response, "usage") and response.usage:
                self._total_tokens += response.usage.total_tokens or 0
                self._prompt_tokens += response.usage.prompt_tokens or 0
                self._completion_tokens += response.usage.completion_tokens or 0
            else:
                self._usage_missing_calls += 1
            if response.choices[0].finish_reason == "length":
                raise ValueError(
                    "Model output was truncated; increase max_tokens or use a smaller mode"
                )
            content = response.choices[0].message.content or ""
            return content.strip()

    async def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """
        Send a completion request and parse the response as JSON.

        Handles common issues like markdown code fences around JSON.
        """
        raw = await self.complete(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
        )

        return parse_json_response(raw)

    @property
    def stats(self) -> dict:
        """Return usage statistics."""
        return {
            "total_calls": self._total_calls,
            "total_tokens": self._total_tokens,
            "model": self.config.model,
            "prompt_tokens": self._prompt_tokens,
            "completion_tokens": self._completion_tokens,
            "requests": self._requests,
            "usage_missing_calls": self._usage_missing_calls,
        }


def parse_json_response(raw: str) -> dict:
    """
    Parse a JSON response from an LLM, handling common formatting issues.

    LLMs often wrap JSON in markdown code fences or include extra text.
    This function robustly extracts and parses the JSON.
    """
    # Try direct parse first
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Expected one JSON object from the model")
        return parsed
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code fence
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", raw, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1).strip())
            if not isinstance(parsed, dict):
                raise ValueError("Expected one JSON object from the model")
            return parsed
        except json.JSONDecodeError:
            pass

    # Try finding the first { ... } block
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse a JSON object from the model response")
