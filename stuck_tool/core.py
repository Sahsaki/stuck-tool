"""Adaptive, bounded deliberation with compact shared evidence."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Callable

from stuck_tool.display import console, print_header, print_phase
from stuck_tool.images import validate_images
from stuck_tool.llm import LLMClient, LLMConfig
from stuck_tool.models import (
    AnalystReport,
    Approach,
    DiscussionMessage,
    FinalRecommendation,
    StuckResult,
    UserEvaluation,
)
from stuck_tool.personas import MODES, PLANNING, SYSTEM, Persona, SituationPlan


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


async def parallel(coroutines):
    tasks = [asyncio.create_task(coro) for coro in coroutines]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


class StuckEngine:
    def __init__(
        self,
        llm_config: LLMConfig | None = None,
        discussion_rounds: int | None = None,
        quiet: bool = False,
        on_progress: Callable[[str, float], None] | None = None,
        *,
        mode: str = "full",
    ):
        if mode not in MODES:
            raise ValueError(f"Unknown mode: {mode}. Choose from {', '.join(MODES)}")
        self.mode = mode
        self.profile = MODES[mode]
        self.discussion_rounds = (
            self.profile.rounds if discussion_rounds is None else discussion_rounds
        )
        if type(self.discussion_rounds) is not int or not 0 <= self.discussion_rounds <= 3:
            raise ValueError("discussion_rounds must be an integer from 0 to 3")
        self.client = LLMClient(llm_config)
        self.quiet = quiet
        self.on_progress = on_progress

    async def _ask(
        self,
        task,
        evidence,
        limit,
        persona: Persona | None = None,
        images: list[tuple[str, bytes]] | None = None,
    ):
        role = ""
        if persona:
            role = f"\nYour assigned simulated role: {compact(persona.model_dump())}"
        return await self.client.complete_json(
            system_prompt=SYSTEM + role + "\n" + task,
            user_prompt=compact(evidence),
            max_tokens=min(limit, self.client.config.max_tokens),
            images=images,
        )

    def _progress(self, phase, description):
        if not self.quiet:
            print_phase(phase, description, "•", "")
        if self.on_progress:
            self.on_progress(description.lower(), 1.0)

    async def run(
        self, problem: str, images: list[tuple[str, bytes]] | None = None
    ) -> StuckResult:
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError("Provide a non-empty problem description")
        if len(problem) > 20000:
            raise ValueError("Problem exceeds 20,000 characters; provide a focused description")
        problem = problem.strip()
        images = validate_images(images)
        before = self.client.stats
        if not self.quiet:
            print_header()
            p = self.profile
            console.print(
                f"{self.mode}: {p.approaches} approaches, {p.users} simulated users, "
                f"{p.analysts} analysts; {p.calls(self.discussion_rounds)} planned calls "
                "(retries can add calls).",
                markup=False,
            )
        self._progress(0, "Plan the panel")
        plan = SituationPlan.model_validate(
            await self._ask(
                PLANNING.format(
                    approaches=self.profile.approaches,
                    users=self.profile.users,
                    analysts=self.profile.analysts,
                ),
                {"problem": problem},
                8000 if self.mode == "deepdive" else 4000,
                images=images,
            )
        )
        plan.check(self.profile)
        context = {
            "problem": problem,
            "situation": plan.situation,
            "constraints": plan.constraints,
            "unknowns": plan.unknowns,
            "criteria": plan.criteria,
        }
        if images:
            context["visual_observations"] = plan.visual_observations

        self._progress(1, "Generate distinct approaches")
        approaches = await self._approaches(context, plan)
        evidence = {**context, "approaches": [a.model_dump() for a in approaches]}

        self._progress(2, "Evaluate every approach")
        evaluations = list(
            await parallel(
                self._evaluate(evidence, user, self.profile.approaches) for user in plan.users
            )
        )
        # Discussions omit plans already evaluated; all per-approach feedback survives.
        reviews = {
            "review_columns": ["approach_id", "rating", "likes", "dislikes", "would_use"],
            "users": [
                {
                    "name": e.user_name,
                    "role": e.persona_tag,
                    "favorite": e.favorite_id,
                    "thoughts": e.overall_thoughts,
                    "reviews": [
                        [r.approach_id, r.rating, r.likes, r.dislikes, r.would_use]
                        for r in e.reviews
                    ],
                }
                for e in evaluations
            ],
        }
        user_discussion = await self._discuss(
            plan.users, {**context, "evaluations": reviews}, "User Persona"
        )

        self._progress(3, "Analyze feedback")
        analytical_evidence = {
            **evidence,
            "evaluations": reviews,
            "user_discussion": [m.model_dump() for m in user_discussion],
        }
        reports = list(
            await parallel(
                self._analyze(analytical_evidence, analyst) for analyst in plan.analysts[:-1]
            )
        )
        analyst_discussion = await self._discuss(
            plan.analysts[:-1],
            {**context, "reports": [r.model_dump() for r in reports]},
            "Data Analyst",
        )

        self._progress(4, "Choose a recommendation")
        recommendation = await self._verdict(
            analytical_evidence, reports, analyst_discussion, plan.analysts[-1], approaches
        )
        after = self.client.stats
        usage = {
            key: after[key] - before[key]
            for key in (
                "total_calls",
                "total_tokens",
                "prompt_tokens",
                "completion_tokens",
                "requests",
                "usage_missing_calls",
            )
        }
        usage["model"] = after["model"]
        result = StuckResult(
            problem=problem,
            mode=self.mode,
            situation_plan=plan.model_dump(),
            usage=usage,
            approaches=approaches,
            user_evaluations=evaluations,
            user_discussion=user_discussion,
            analyst_reports=reports,
            analyst_discussion=analyst_discussion,
            recommendation=recommendation,
        )
        if not self.quiet:
            console.print(
                f"Usage: {usage['requests']} requests, "
                f"{usage['total_tokens']:,} reported tokens "
                f"({usage['usage_missing_calls']} responses without usage).",
                markup=False,
            )
        return result

    async def _approaches(self, context, plan):
        # Quick/express batch directions into fewer generator agents, keeping all ten.
        batches = [
            plan.directions[i :: self.profile.generators] for i in range(self.profile.generators)
        ]
        task = """Develop only your assigned directions. Respect their different mechanisms.
You can see the other directions to avoid duplicating them. Each plan: 3-5 concrete
steps, summary <=50 words, up to 3 pros and cons. Omit code sketches unless essential.
JSON: {"approaches":[{"id":1,"name":"name","philosophy":"core tradeoff",
"summary":"summary","detailed_plan":"steps","pros":[],"cons":[],
"effort_estimate":"estimate with assumptions","code_sketch":""}]}"""

        async def generate(batch, index):
            data = await self._ask(
                task,
                {
                    **context,
                    "all_directions": [d.model_dump() for d in plan.directions],
                    "assigned_ids": [d.id for d in batch],
                },
                650 * len(batch),
            )
            items = [
                Approach.model_validate({**a, "agent_name": f"Generator {index}"})
                for a in data["approaches"]
            ]
            if sorted(a.id for a in items) != sorted(d.id for d in batch):
                raise ValueError("Generator must return exactly its assigned approach IDs")
            return items

        generated = await parallel(generate(batch, i) for i, batch in enumerate(batches, 1))
        approaches = sorted([a for batch in generated for a in batch], key=lambda a: a.id)
        if len({a.name.strip().casefold() for a in approaches}) != len(approaches):
            raise ValueError("Generated approaches must have distinct names")
        return approaches

    async def _evaluate(self, evidence, persona, count):
        data = await self._ask(
            """Evaluate EVERY approach once against the criteria, from your assigned needs.
This is a simulated review, not an actual trial. Likes and dislikes <=15 words each.
JSON: {"reviews":[{"approach_id":1,"rating":7,"likes":"specific reason",
"dislikes":"specific concern","would_use":true}],"favorite_id":1,
"overall_thoughts":"<=60 words, include a tension or uncertainty"}""",
            evidence,
            180 * count + 200,
            persona,
        )
        evaluation = UserEvaluation.model_validate(
            {
                **data,
                "user_name": persona.name,
                "persona_tag": persona.role,
            }
        )
        if sorted(r.approach_id for r in evaluation.reviews) != list(range(1, count + 1)):
            raise ValueError("Each user must review every approach exactly once")
        self._check_id(evaluation.favorite_id)
        return evaluation

    async def _discuss(self, panel, evidence, role):
        history = []
        for round_number in range(1, self.discussion_rounds + 1):
            # Only the last round is repeated; complete transcripts stay in the result.
            previous = [m.model_dump() for m in history if m.round_number == round_number - 1]

            async def turn(persona):
                data = await self._ask(
                    """Discuss a specific disagreement or tradeoff with a named panel member.
Respond to their supplied review/report or previous message. Explain agreement,
disagreement, or a changed view; add evidence limits. <=90 words. Do not invent replies.
JSON: {"responding_to":"panel member name or everyone","message":"contribution"}""",
                    {**evidence, "previous_round": previous, "panel": [p.name for p in panel]},
                    350,
                    persona,
                )
                if data["responding_to"] not in {p.name for p in panel} | {"everyone"}:
                    raise ValueError("Discussion response names a nonexistent panel member")
                return DiscussionMessage(
                    speaker=persona.name, role=role, round_number=round_number, **data
                )

            history.extend(await parallel(turn(p) for p in panel))
        return history

    async def _analyze(self, evidence, persona):
        data = await self._ask(
            """Apply your methodology to all reviews, disagreements, constraints and plans.
Scores are simulated preferences, not population statistics or real user research.
Explain decisive tradeoffs and missing evidence. Analysis <=180 words; up to 4 findings
and risks. JSON: {"analysis":"reasoning","recommended_approach_id":1,
"confidence":0.6,"key_findings":[],"risks":[]}""",
            evidence,
            1000,
            persona,
        )
        report = AnalystReport.model_validate(
            {
                **data,
                "analyst_name": persona.name,
                "specialty": persona.role,
            }
        )
        self._check_id(report.recommended_approach_id)
        return report

    async def _verdict(self, evidence, reports, discussion, chief, approaches):
        data = await self._ask(
            """Choose one existing approach using the criteria, reviews and panel analysis.
Explain any departure from the panel majority. Preserve material dissent and unknowns.
Confidence is subjective, not statistical. Give actionable steps and validation needed.
JSON: {"winning_approach_id":1,"summary":"<=80 words",
"detailed_reasoning":"<=200 words","implementation_roadmap":"3-5 concrete steps",
"dissenting_views":[],"caveats":[]}""",
            {
                **evidence,
                "analyst_reports": [r.model_dump() for r in reports],
                "analyst_discussion": [m.model_dump() for m in discussion],
            },
            1800,
            chief,
        )
        self._check_id(data["winning_approach_id"])
        winner = approaches[data["winning_approach_id"] - 1]
        # Votes come from actual reports plus the chief, never model-invented counts.
        votes = Counter(r.recommended_approach_id for r in reports)
        votes[winner.id] += 1
        share = votes[winner.id] / self.profile.analysts
        consensus = (
            "unanimous"
            if share == 1
            else "strong"
            if share >= 0.8
            else "moderate"
            if share > 0.5
            else "split"
        )
        return FinalRecommendation.model_validate(
            {
                **data,
                "winning_approach_name": winner.name,
                "vote_breakdown": dict(votes),
                "consensus_level": consensus,
            }
        )

    def _check_id(self, approach_id):
        if type(approach_id) is not int or not 1 <= approach_id <= self.profile.approaches:
            raise ValueError("Response references a nonexistent approach")


async def run_stuck(
    problem: str,
    model: str = "",
    api_key: str = "",
    discussion_rounds: int | None = None,
    quiet: bool = False,
    *,
    mode: str = "full",
    images: list[tuple[str, bytes]] | None = None,
) -> StuckResult:
    engine = StuckEngine(
        llm_config=LLMConfig(model=model, api_key=api_key),
        discussion_rounds=discussion_rounds,
        quiet=quiet,
        mode=mode,
    )
    return await engine.run(problem, images=images)
