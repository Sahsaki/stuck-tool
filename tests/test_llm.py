import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import litellm
import pytest

from stuck_tool.llm import LLMClient, LLMConfig, parse_json_response


@pytest.mark.parametrize("raw", ['{"ok":true}', '```json\n{"ok":true}\n```', 'Answer: {"ok":true}'])
def test_parse_object(raw):
    assert parse_json_response(raw) == {"ok": True}


@pytest.mark.parametrize("raw", ["[]", "null", "```json\n[]\n```", "not json"])
def test_reject_nonobjects(raw):
    with pytest.raises(ValueError):
        parse_json_response(raw)


def response(usage=True, finish="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'), finish_reason=finish)
        ],
        usage=SimpleNamespace(total_tokens=12, prompt_tokens=8, completion_tokens=4)
        if usage
        else None,
    )


async def test_limits_zero_temperature_and_request_scoped_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "existing-key")
    provider = AsyncMock(return_value=response())
    monkeypatch.setattr(litellm, "acompletion", provider)
    client = LLMClient(LLMConfig(model="test", api_key="explicit-key", retry_count=0))
    assert await client.complete_json("system", "problem", temperature=0, max_tokens=100) == {
        "ok": True
    }
    kwargs = provider.call_args.kwargs
    assert kwargs["temperature"] == 0
    assert kwargs["max_tokens"] == 100
    assert kwargs["api_key"] == "explicit-key"
    assert kwargs["num_retries"] == 0
    assert os.environ["OPENAI_API_KEY"] == "existing-key"
    assert client.stats["total_tokens"] == 12


async def test_missing_usage_is_visible(monkeypatch):
    monkeypatch.setattr(litellm, "acompletion", AsyncMock(return_value=response(usage=False)))
    client = LLMClient(LLMConfig(model="test"))
    await client.complete_json("system", "problem")
    assert client.stats["usage_missing_calls"] == 1


async def test_truncated_output_is_not_retried(monkeypatch):
    provider = AsyncMock(return_value=response(finish="length"))
    monkeypatch.setattr(litellm, "acompletion", provider)
    client = LLMClient(LLMConfig(model="test"))
    with pytest.raises(ValueError, match="truncated"):
        await client.complete_json("system", "problem")
    assert provider.call_count == 1


async def test_permanent_error_is_not_retried(monkeypatch):
    error = litellm.AuthenticationError(message="Invalid key", model="test", llm_provider="openai")
    provider = AsyncMock(side_effect=error)
    monkeypatch.setattr(litellm, "acompletion", provider)
    client = LLMClient(LLMConfig(model="test"))
    with pytest.raises(RuntimeError):
        await client.complete_json("system", "problem")
    assert provider.call_count == client.stats["requests"] == 1


async def test_transient_retry_is_bounded_and_counted(monkeypatch):
    error = litellm.RateLimitError(message="Slow down", model="test", llm_provider="openai")
    provider = AsyncMock(side_effect=[error, response()])
    monkeypatch.setattr(litellm, "acompletion", provider)
    monkeypatch.setattr("stuck_tool.llm.asyncio.sleep", AsyncMock())
    client = LLMClient(LLMConfig(model="test", retry_count=1))
    await client.complete_json("system", "problem")
    assert provider.call_count == client.stats["requests"] == 2
    assert client.stats["total_calls"] == 1


@pytest.mark.parametrize(
    "options", [{"max_concurrent": 0}, {"max_tokens": 0}, {"timeout": 0}, {"retry_count": 3}]
)
def test_bad_limits_fail_early(options):
    with pytest.raises(ValueError):
        LLMConfig(model="test", **options)


def test_config_repr_omits_api_key():
    assert "canary-private-credential" not in repr(
        LLMConfig(model="test", api_key="canary-private-credential")
    )


def test_plugin_config_uses_plugin_data_and_environment_wins(monkeypatch, tmp_path):
    (tmp_path / ".stuck-tool.json").write_text(
        '{"model":"anthropic/test","api_key":"file-key","api_base":"https://file"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("STUCK_TOOL_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("STUCK_TOOL_API_KEY", "environment-key")
    config = LLMConfig()
    assert config.model == "anthropic/test"
    assert config.api_key == "environment-key"
    assert config.api_base == "https://file"


def test_plugin_config_errors_do_not_echo_content(monkeypatch, tmp_path):
    secret = "canary-private-credential"
    (tmp_path / ".stuck-tool.json").write_text(secret, encoding="utf-8")
    monkeypatch.setenv("STUCK_TOOL_CONFIG_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="valid JSON") as error:
        LLMConfig(model="test")
    assert secret not in str(error.value)


@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
async def test_provider_errors_do_not_expose_credentials(monkeypatch, caplog, error_type):
    secret = "canary-private-credential"
    provider = AsyncMock(side_effect=error_type(f"Authorization failed: {secret}"))
    monkeypatch.setattr(litellm, "acompletion", provider)
    client = LLMClient(LLMConfig(model="test", api_key=secret))
    with pytest.raises(RuntimeError) as error:
        await client.complete_json("system", "private problem")
    assert secret not in str(error.value)
    assert secret not in caplog.text
    assert error.value.__suppress_context__
    assert provider.call_count == 1
