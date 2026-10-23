"""Check public CLI and real in-memory MCP protocol integration."""

import json
import sys

import pytest
from click.testing import CliRunner
from mcp.shared.memory import create_connected_server_and_client_session
from test_pipeline import fake_provider

from stuck_tool.cli import deepdive, main
from stuck_tool.mcp_server import create_mcp_server
from stuck_tool.models import ApproachReview
from stuck_tool.personas import MODES


@pytest.mark.parametrize(
    "mode,flag",
    [
        ("full", []),
        ("quick", ["--quick"]),
        ("express", ["--express"]),
        ("deepdive", ["--deepdive"]),
    ],
)
def test_cli_modes_and_exports(monkeypatch, tmp_path, mode, flag):
    requests = fake_provider(monkeypatch, mode)
    report = tmp_path / "report.md"
    raw = tmp_path / "result.json"
    result = CliRunner().invoke(
        main,
        [
            *flag,
            "--model",
            "test-model",
            "--quiet",
            "--output",
            str(report),
            "--json-output",
            str(raw),
            "Plan a community garden",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "RECOMMENDATION: Approach 2" in result.output
    assert "PROPOSED CHANGES:" in result.output
    assert "Want to implement these proposed changes?" in result.output
    assert "hasn't changed any files" in result.output
    assert "All Approaches" in report.read_text(encoding="utf-8")
    data = json.loads(raw.read_text(encoding="utf-8"))
    assert data["mode"] == mode
    assert data["usage"]["requests"] == len(requests) == MODES[mode].calls(MODES[mode].rounds)


@pytest.mark.parametrize(
    "arguments",
    [
        ["--quick", "--deepdive"],
        ["--express", "--quick"],
        ["--rounds", "-1"],
        ["--rounds", "4"],
        ["--max-concurrent", "0"],
    ],
)
def test_cli_invalid_flags_do_not_call_provider(monkeypatch, arguments):
    requests = fake_provider(monkeypatch, "quick")
    result = CliRunner().invoke(main, [*arguments, "Plan a garden"])
    assert result.exit_code == 2
    assert not requests


def test_cli_pipe(monkeypatch):
    requests = fake_provider(monkeypatch, "express")
    result = CliRunner().invoke(
        main, ["--express", "--quiet", "--model", "test-model"], input="Plan the garden"
    )
    assert result.exit_code == 0
    assert len(requests) == 6


def test_deepdive_command_alias(monkeypatch, tmp_path):
    requests = fake_provider(monkeypatch, "deepdive")
    path = tmp_path / "deepdive.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stuck-deepdive",
            "--model",
            "test-model",
            "--quiet",
            "--json-output",
            str(path),
            "Plan the garden",
        ],
    )
    with pytest.raises(SystemExit) as error:
        deepdive()
    assert error.value.code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["mode"] == "deepdive"
    assert len(requests) == 138


async def test_mcp_session_default_compact_report_and_schema(monkeypatch, capsys):
    requests = fake_provider(monkeypatch, "quick")
    server, _ = create_mcp_server()
    async with create_connected_server_and_client_session(server) as session:
        listed = await session.list_tools()
        tool = listed.tools[0]
        assert tool.name == "stuck"
        assert tool.inputSchema["properties"]["mode"]["enum"] == list(MODES)
        assert tool.inputSchema["properties"]["full_report"]["default"] is False
        result = await session.call_tool(
            "stuck", {"problem": "Plan a community garden", "model": "test-model"}
        )
        assert not result.isError
        assert "Pilot solution two" in result.content[0].text
        assert "Want to implement these proposed changes?" in result.content[0].text
        assert "All Approaches" not in result.content[0].text
        assert "Other analysts preferred" in result.content[0].text
    assert len(requests) == 15
    assert not capsys.readouterr().out


async def test_mcp_deepdive_full_report(monkeypatch):
    requests = fake_provider(monkeypatch, "deepdive")
    server, _ = create_mcp_server()
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "stuck",
            {
                "problem": "Plan the garden",
                "model": "test-model",
                "mode": "deepdive",
                "full_report": True,
            },
        )
        assert not result.isError
        assert "All Approaches" in result.content[0].text
        assert "Solution 20" in result.content[0].text
        assert "Analyst Discussion" in result.content[0].text
    assert len(requests) == 138


@pytest.mark.parametrize(
    "arguments",
    [
        {"problem": ""},
        {"problem": "garden", "mode": "unknown"},
        {"problem": "garden", "full_report": "yes"},
    ],
)
async def test_mcp_invalid_input_no_provider_call(monkeypatch, arguments):
    requests = fake_provider(monkeypatch, "quick")
    server, _ = create_mcp_server()
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("stuck", arguments)
        assert "error" in result.content[0].text.lower()
    assert not requests


async def invalid_private_response(self, problem):
    ApproachReview.model_validate(
        {
            "approach_id": 1,
            "rating": "canary-private-feedback",
            "likes": "",
            "dislikes": "",
            "would_use": True,
        }
    )


def test_cli_validation_error_omits_model_input(monkeypatch):
    monkeypatch.setattr("stuck_tool.core.StuckEngine.run", invalid_private_response)
    result = CliRunner().invoke(main, ["--model", "test-model", "Plan the garden"])
    assert result.exit_code == 1
    assert "failed validation" in result.output
    assert "canary-private-feedback" not in result.output


async def test_mcp_validation_error_omits_model_input(monkeypatch, caplog):
    monkeypatch.setattr("stuck_tool.core.StuckEngine.run", invalid_private_response)
    server, _ = create_mcp_server()
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("stuck", {"problem": "garden", "model": "test-model"})
        assert "failed validation" in result.content[0].text
        assert "canary-private-feedback" not in result.content[0].text
    assert "canary-private-feedback" not in caplog.text
