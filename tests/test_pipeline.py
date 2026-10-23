"""Exercise complete modes without a network connection or API key."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from stuck_tool.core import StuckEngine, parallel, run_stuck
from stuck_tool.display import format_result_markdown
from stuck_tool.llm import LLMConfig
from stuck_tool.personas import MODES


def panel(profile, domain="community garden"):
    return {
        "situation": f"Choose a plan for a {domain}",
        "constraints": ["Limited volunteer time"],
        "unknowns": ["Available budget"],
        "criteria": ["Feasibility", "Accessibility"],
        "directions": [
            {"id": i, "name": f"Method {i}", "method": f"Distinct mechanism {i} for {domain}"}
            for i in range(1, profile.approaches + 1)
        ],
        "users": [
            {"name": f"Gardener {i}", "role": "Volunteer", "perspective": f"Priority {i}"}
            for i in range(profile.users)
        ],
        "analysts": [
            {"name": f"Analyst {i}", "role": "Community planning", "perspective": f"Method {i}"}
            for i in range(profile.analysts)
        ],
    }


def fake_provider(monkeypatch, mode, fault=None):
    profile = MODES[mode]
    requests = []

    async def completion(**kwargs):
        requests.append(kwargs)
        evidence = json.loads(kwargs["messages"][1]["content"])
        if set(evidence) == {"problem"}:
            data = panel(profile)
            if fault == "duplicate-persona":
                data["users"][1] = data["users"][0]
        elif "assigned_ids" in evidence:
            data = {
                "approaches": [
                    {
                        "id": i,
                        "name": f"Solution {i}",
                        "philosophy": f"Mechanism {i}",
                        "summary": f"Summary {i}",
                        "detailed_plan": "1. Ask volunteers. 2. Pilot.",
                        "pros": ["Feasible"],
                        "cons": ["Needs validation"],
                    }
                    for i in evidence["assigned_ids"]
                ]
            }
            if fault == "missing-approach":
                data["approaches"].pop()
        elif "previous_round" in evidence:
            data = {"responding_to": "everyone", "message": "Budget concerns remain unresolved."}
        elif "analyst_reports" in evidence:
            data = {
                "winning_approach_id": 999 if fault == "bad-winner" else 2,
                "winning_approach_name": "Invented name",
                "vote_breakdown": {"2": 999},
                "consensus_level": "unanimous",
                "summary": "Pilot solution two.",
                "detailed_reasoning": "Accessibility outweighs the majority's convenience.",
                "implementation_roadmap": "Ask volunteers; run a pilot; measure attendance.",
                "dissenting_views": ["Other analysts preferred solution one."],
                "caveats": ["Simulated feedback requires real validation."],
            }
        elif "evaluations" in evidence:
            data = {
                "analysis": "Review volunteer constraints.",
                "recommended_approach_id": 1,
                "confidence": 0.6,
                "key_findings": ["Time is scarce"],
                "risks": ["Budget unknown"],
            }
        else:
            data = {
                "reviews": [
                    {
                        "approach_id": a["id"],
                        "rating": 8,
                        "likes": "Accessible",
                        "dislikes": "Time | budget\nuncertain",
                        "would_use": True,
                    }
                    for a in evidence["approaches"]
                ],
                "favorite_id": 1,
                "overall_thoughts": "Validate with actual volunteers.",
            }
            if fault == "missing-review":
                data["reviews"].pop()
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(data)), finish_reason="stop"
                )
            ],
            usage=SimpleNamespace(total_tokens=30, prompt_tokens=20, completion_tokens=10),
        )

    monkeypatch.setattr("stuck_tool.llm.litellm.acompletion", completion)
    return requests


@pytest.mark.parametrize(
    "mode,calls", [("full", 54), ("quick", 15), ("express", 6), ("deepdive", 138)]
)
async def test_complete_modes(monkeypatch, mode, calls):
    requests = fake_provider(monkeypatch, mode)
    engine = StuckEngine(LLMConfig(model="test-model"), mode=mode, quiet=True)
    result = await engine.run("How should our community garden organize volunteers?")
    profile = MODES[mode]
    assert len(requests) == calls == profile.calls(profile.rounds)
    assert [a.id for a in result.approaches] == list(range(1, profile.approaches + 1))
    assert len({a.agent_name for a in result.approaches}) == profile.generators
    assert len(result.user_evaluations) == profile.users
    assert all(len(e.reviews) == profile.approaches for e in result.user_evaluations)
    assert len(result.situation_plan["analysts"]) == profile.analysts
    assert len(result.analyst_reports) == profile.analysts - 1  # Chief is the recommendation.
    assert len(result.user_discussion) == profile.users * profile.rounds
    assert len(result.analyst_discussion) == (profile.analysts - 1) * profile.rounds
    assert result.recommendation.winning_approach_name == "Solution 2"
    assert result.recommendation.vote_breakdown == {1: profile.analysts - 1, 2: 1}
    assert result.recommendation.consensus_level == "split"
    assert result.usage["requests"] == calls
    assert result.usage["total_tokens"] == calls * 30
    assert result.usage["prompt_tokens"] == calls * 20
    assert result.usage["completion_tokens"] == calls * 10
    assert all(0 < r["max_tokens"] <= 8192 for r in requests)
    assert max(r["max_tokens"] for r in requests) < 8192
    full = format_result_markdown(result)
    short = format_result_markdown(result, full=False)
    assert f"/{profile.analysts}" in full
    assert "Time \\| budget uncertain" in full
    assert "Priority 0" in full
    assert "Simulated perspectives" in short
    assert "Want to implement these proposed changes?" in short
    assert "hasn't changed any files" in short
    assert "Other analysts preferred" in short
    assert "All Approaches" not in short
    assert len(short) < len(full)
    analyst_request = next(
        json.loads(r["messages"][1]["content"])
        for r in requests
        if '"review_columns"' in r["messages"][1]["content"]
    )
    assert analyst_request["evaluations"]["users"][0]["reviews"][0][3].startswith("Time")
    if profile.rounds:
        discussions = [
            json.loads(r["messages"][1]["content"])
            for r in requests
            if '"previous_round"' in r["messages"][1]["content"]
        ]
        assert all("approaches" not in d for d in discussions)
        if profile.rounds > 1:
            assert max(len(d["previous_round"]) for d in discussions) == profile.users


@pytest.mark.parametrize(
    "fault,message",
    [
        ("duplicate-persona", "distinct users"),
        ("missing-approach", "assigned approach IDs"),
        ("missing-review", "every approach exactly once"),
        ("bad-winner", "nonexistent approach"),
    ],
)
async def test_invalid_model_output_fails_without_repair_calls(monkeypatch, fault, message):
    requests = fake_provider(monkeypatch, "quick", fault)
    engine = StuckEngine(LLMConfig(model="test-model"), mode="quick", quiet=True)
    with pytest.raises(ValueError, match=message):
        await engine.run("Plan a community garden")
    assert len(requests) <= MODES["quick"].calls(1)


async def test_reuse_reports_per_run_usage(monkeypatch):
    fake_provider(monkeypatch, "express")
    engine = StuckEngine(LLMConfig(model="test-model"), mode="express", quiet=True)
    first = await engine.run("Plan the garden")
    second = await engine.run("Reconsider the garden")
    assert first.usage == second.usage
    assert second.usage["requests"] == 6


async def test_api_round_override(monkeypatch):
    requests = fake_provider(monkeypatch, "quick")
    result = await run_stuck(
        "Plan the garden", model="test-model", mode="quick", discussion_rounds=0, quiet=True
    )
    assert not result.user_discussion
    assert len(requests) == 10


@pytest.mark.parametrize("problem", ["", "  ", None, "a" * 20001])
async def test_invalid_problem_does_not_call_provider(monkeypatch, problem):
    requests = fake_provider(monkeypatch, "quick")
    engine = StuckEngine(LLMConfig(model="test-model"), quiet=True)
    with pytest.raises(ValueError):
        await engine.run(problem)
    assert not requests


@pytest.mark.parametrize(
    "options",
    [
        {"mode": "unknown"},
        {"discussion_rounds": -1},
        {"discussion_rounds": 4},
        {"discussion_rounds": True},
    ],
)
def test_invalid_engine_options(options):
    with pytest.raises(ValueError):
        StuckEngine(LLMConfig(model="test-model"), **options)


async def test_failed_parallel_phase_cancels_other_paid_work():
    cancelled = asyncio.Event()
    started = asyncio.Event()

    async def running():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def failing():
        await started.wait()
        raise ValueError("bad output")

    with pytest.raises(ValueError):
        await parallel([running(), failing()])
    assert cancelled.is_set()
