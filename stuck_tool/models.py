"""Data models for the stuck-tool deliberation pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Approach(BaseModel):
    """A solution approach generated from a situation-specific direction."""

    id: int = Field(ge=1, description="Unique approach identifier")
    name: str = Field(min_length=1, description="Short memorable name for this approach")
    agent_name: str = Field(description="Name of the agent who generated this")
    philosophy: str = Field(description="The core philosophy behind this approach")
    summary: str = Field(description="One-paragraph executive summary")
    detailed_plan: str = Field(description="Full detailed plan with steps")
    pros: list[str] = Field(description="Key advantages of this approach")
    cons: list[str] = Field(description="Key disadvantages or risks")
    code_sketch: str = Field(default="", description="Optional code sketch or pseudocode")
    effort_estimate: str = Field(default="", description="Rough effort/time estimate")


class ApproachReview(BaseModel):
    """A single user's review of a single approach."""

    approach_id: int = Field(ge=1)
    rating: int = Field(ge=1, le=10, description="Rating from 1 (terrible) to 10 (perfect)")
    likes: str = Field(description="What this user likes about the approach")
    dislikes: str = Field(description="What this user dislikes about the approach")
    would_use: bool = Field(description="Whether this user would actually use this approach")


class UserEvaluation(BaseModel):
    """Complete evaluation from a simulated user agent."""

    user_name: str = Field(description="Display name of the user persona")
    persona_tag: str = Field(description="Short persona descriptor")
    reviews: list[ApproachReview] = Field(description="Review of each approach")
    favorite_id: int = Field(description="ID of their favorite approach")
    overall_thoughts: str = Field(description="General thoughts across all approaches")


class DiscussionMessage(BaseModel):
    """A single message in a multi-agent discussion."""

    speaker: str = Field(description="Name of the speaker")
    role: str = Field(description="Role tag (e.g., 'User Persona', 'Analyst')")
    message: str = Field(description="The message content")
    responding_to: str = Field(default="", description="Who they are responding to, if anyone")
    round_number: int = Field(description="Discussion round number")


class AnalystReport(BaseModel):
    """Analysis report from a situation-specific analyst."""

    analyst_name: str = Field(description="Name of the analyst")
    specialty: str = Field(description="Analyst specialty area")
    analysis: str = Field(description="Detailed analysis text")
    recommended_approach_id: int = Field(description="Which approach they recommend")
    confidence: float = Field(ge=0, le=1, description="Confidence level 0.0-1.0")
    key_findings: list[str] = Field(description="Bullet-point key findings")
    risks: list[str] = Field(default_factory=list, description="Identified risks")


class FinalRecommendation(BaseModel):
    """The final synthesized recommendation from the analyst panel."""

    winning_approach_id: int = Field(description="ID of the winning approach")
    winning_approach_name: str = Field(description="Name of the winning approach")
    consensus_level: str = Field(description="unanimous / strong / moderate / split")
    vote_breakdown: dict[int, int] = Field(description="approach_id -> number of analyst votes")
    summary: str = Field(description="Executive summary of the recommendation")
    detailed_reasoning: str = Field(description="Full reasoning behind the choice")
    implementation_roadmap: str = Field(description="Suggested implementation steps")
    dissenting_views: list[str] = Field(
        default_factory=list, description="Notable dissenting opinions"
    )
    caveats: list[str] = Field(default_factory=list, description="Important caveats to consider")


class StuckResult(BaseModel):
    """Complete result from the stuck-tool deliberation pipeline."""

    problem: str = Field(description="The original problem statement")
    mode: str = "full"
    situation_plan: dict = Field(default_factory=dict)
    usage: dict = Field(default_factory=dict)
    approaches: list[Approach] = Field(description="The generated approaches")
    user_evaluations: list[UserEvaluation] = Field(description="Simulated user evaluations")
    user_discussion: list[DiscussionMessage] = Field(description="User discussion transcript")
    analyst_reports: list[AnalystReport] = Field(description="Independent analyst reports")
    analyst_discussion: list[DiscussionMessage] = Field(description="Analyst discussion transcript")
    recommendation: FinalRecommendation = Field(description="Final recommendation")
