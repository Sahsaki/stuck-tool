"""
Rich terminal display helpers for stuck-tool output.

Provides beautiful, informative progress displays and result formatting.
"""

from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text

from stuck_tool.models import StuckResult

console = Console()


def create_progress() -> Progress:
    """Create a styled progress bar for tracking pipeline phases."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )


def print_header():
    """Print the stuck-tool header banner."""
    banner = Text()
    banner.append("🔧 ", style="bold")
    banner.append("stuck-tool", style="bold magenta")
    banner.append(" — ", style="dim")
    banner.append("Multi-Agent Deliberation Engine", style="italic cyan")

    console.print(Panel(banner, border_style="magenta", padding=(0, 2)))


def print_phase(phase_num: int, title: str, emoji: str, description: str):
    """Print a phase header."""
    console.print(
        f"  {emoji} [bold cyan]Phase {phase_num}:[/] [bold]{title}[/]",
    )
    if description:
        console.print(f"     [dim]{description}[/]")


def print_approach(approach_id: int, name: str, emoji: str, agent_name: str, summary: str):
    """Print a generated approach summary."""
    console.print(
        Panel(
            f"[italic]{summary}[/]",
            title=f"{emoji} Approach {approach_id}: {name}",
            subtitle=f"by {agent_name}",
            border_style="green",
            padding=(0, 2),
        )
    )


def print_user_reaction(name: str, emoji: str, favorite_id: int, thoughts: str):
    """Print a user's quick reaction."""
    console.print(f"  {emoji} [bold]{name}[/] → Favorite: Approach {favorite_id}")


def print_discussion_message(speaker: str, emoji: str, message: str, responding_to: str = ""):
    """Print a discussion message."""
    header = f"{emoji} {speaker}"
    if responding_to and responding_to != "everyone":
        header += f" → @{responding_to}"

    # Truncate long messages for display
    display_msg = message if len(message) <= 200 else message[:197] + "..."
    console.print(f"  {header}: [dim]{display_msg}[/]")


def print_analyst_vote(name: str, emoji: str, approach_id: int, confidence: float):
    """Print an analyst's vote."""
    bar = "█" * int(confidence * 10) + "░" * (10 - int(confidence * 10))
    console.print(
        f"  {emoji} [bold]{name}[/] → Approach {approach_id} "
        f"[dim]confidence:[/] [{_confidence_color(confidence)}]{bar} {confidence:.0%}[/]"
    )


def _confidence_color(confidence: float) -> str:
    if confidence >= 0.8:
        return "green"
    if confidence >= 0.6:
        return "yellow"
    return "red"


def print_final_result(result: StuckResult):
    """Print the full final result with all details."""
    rec = result.recommendation
    winning = next(a for a in result.approaches if a.id == rec.winning_approach_id)

    # === Winner Panel ===
    console.print()
    winner_text = Text()
    winner_text.append("🏆 ", style="bold")
    winner_text.append("RECOMMENDED: ", style="bold green")
    winner_text.append(f"Approach {winning.id} — {winning.name}\n\n", style="bold white")
    winner_text.append("Consensus: ", style="bold")
    winner_text.append(
        f"{rec.consensus_level.upper()}\n", style=_consensus_style(rec.consensus_level)
    )
    winner_text.append(f"\n{rec.summary}", style="")

    console.print(
        Panel(
            winner_text,
            border_style="green",
            title="[bold green]FINAL RECOMMENDATION",
            padding=(1, 2),
        )
    )

    # === Vote Breakdown ===
    if rec.vote_breakdown:
        total_votes = sum(rec.vote_breakdown.values())
        vote_table = Table(title="Analyst Vote Breakdown", border_style="dim")
        vote_table.add_column("Approach", style="cyan")
        vote_table.add_column("Votes", style="green")

        for aid, votes in sorted(rec.vote_breakdown.items(), key=lambda x: -x[1]):
            approach = next((a for a in result.approaches if a.id == int(aid)), None)
            name = approach.name if approach else f"Approach {aid}"
            bar = "🟢" * votes + "⚪" * (total_votes - votes)
            vote_table.add_row(f"{aid}. {name}", f"{bar} ({votes}/{total_votes})")

        console.print()
        console.print(vote_table)

    # === Detailed Reasoning ===
    console.print()
    console.print(
        Panel(
            Markdown(rec.detailed_reasoning),
            title="[bold]Detailed Reasoning",
            border_style="blue",
            padding=(1, 2),
        )
    )

    # === Implementation Roadmap ===
    if rec.implementation_roadmap:
        console.print()
        console.print(
            Panel(
                Markdown(rec.implementation_roadmap),
                title="[bold cyan]Proposed Changes",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    # === Caveats & Dissent ===
    if rec.caveats or rec.dissenting_views:
        console.print()
        warnings = ""
        if rec.caveats:
            warnings += "**⚠️ Caveats:**\n" + "\n".join(f"- {c}" for c in rec.caveats) + "\n\n"
        if rec.dissenting_views:
            warnings += "**🗣️ Dissenting Views:**\n" + "\n".join(
                f"- {d}" for d in rec.dissenting_views
            )

        console.print(
            Panel(
                Markdown(warnings),
                title="[bold yellow]Things to Watch",
                border_style="yellow",
                padding=(1, 2),
            )
        )

    console.print("\n[bold]Want to implement these proposed changes?[/]")
    console.print("[dim]This tool made a plan; it hasn't changed any files.[/]")


def _consensus_style(level: str) -> str:
    return {
        "unanimous": "bold green",
        "strong": "green",
        "moderate": "yellow",
        "split": "red",
    }.get(level.lower(), "white")


def format_result_markdown(result: StuckResult, *, full: bool = True) -> str:
    """Format the full result as a markdown document."""
    rec = result.recommendation
    winning = next(a for a in result.approaches if a.id == rec.winning_approach_id)

    lines = [
        "# 🔧 stuck-tool Deliberation Report",
        "",
        "Simulated perspectives, not real user testing or measured outcomes.",
        f"Mode: {result.mode}. Requests: {result.usage.get('requests', 'unknown')}. "
        f"Reported tokens: {result.usage.get('total_tokens', 'unknown')} "
        f"(responses missing usage: {result.usage.get('usage_missing_calls', 'unknown')}).",
        "",
        "## Problem",
        "",
        result.problem if full else result.situation_plan.get("situation", result.problem[:500]),
        "",
        "---",
        "",
        f"## 🏆 Recommendation: Approach {winning.id} — {winning.name}",
        "",
        f"**Consensus Level:** {rec.consensus_level}",
        "",
        f"{rec.summary}",
        "",
        "### Detailed Reasoning",
        "",
        f"{rec.detailed_reasoning}",
        "",
        "### Proposed changes",
        "",
        f"{rec.implementation_roadmap}",
        "",
        "### Your call",
        "",
        "Want to implement these proposed changes?",
        "This tool made a plan; it hasn't changed any files.",
        "",
    ]

    # Caveats
    if rec.caveats:
        lines.append("### ⚠️ Caveats")
        lines.append("")
        for c in rec.caveats:
            lines.append(f"- {c}")
        lines.append("")

    # Vote breakdown
    if rec.vote_breakdown:
        total_votes = sum(rec.vote_breakdown.values())
        lines.append("### Analyst Votes")
        lines.append("")
        lines.append("| Approach | Votes |")
        lines.append("|----------|-------|")
        for aid, votes in sorted(rec.vote_breakdown.items(), key=lambda x: -x[1]):
            approach = next((a for a in result.approaches if a.id == int(aid)), None)
            name = approach.name if approach else f"Approach {aid}"
            lines.append(f"| {aid}. {name} | {votes}/{total_votes} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    if rec.dissenting_views:
        lines.extend(["### Dissent", "", *[f"- {d}" for d in rec.dissenting_views], ""])
    if not full:
        return "\n".join(lines)

    plan = result.situation_plan
    if plan:
        lines.extend(["## Situation and panel", "", plan["situation"], ""])
        for key in ("constraints", "unknowns", "criteria"):
            lines.extend([f"**{key.title()}:**", *[f"- {v}" for v in plan[key]], ""])
        for key in ("users", "analysts"):
            lines.append(f"### Simulated {key}")
            for persona in plan[key]:
                lines.append(
                    f"- **{persona['name']} ({persona['role']}):** {persona['perspective']}"
                )
            lines.append("")

    # All approaches
    lines.append("## 📋 All Approaches")
    lines.append("")
    for a in result.approaches:
        lines.append(f"### Approach {a.id}: {a.name}")
        lines.append(f"*Generated by: {a.agent_name}*")
        lines.append("")
        lines.append(f"**Philosophy:** {a.philosophy}")
        lines.append("")
        lines.append(f"{a.summary}")
        lines.append("")
        lines.append("**Detailed Plan:**")
        lines.append(f"{a.detailed_plan}")
        lines.append("")
        if a.pros:
            lines.append("**Pros:**")
            for p in a.pros:
                lines.append(f"- ✅ {p}")
            lines.append("")
        if a.cons:
            lines.append("**Cons:**")
            for c in a.cons:
                lines.append(f"- ❌ {c}")
            lines.append("")
        if a.code_sketch:
            lines.append("**Code Sketch:**")
            lines.append("```")
            lines.append(a.code_sketch)
            lines.append("```")
            lines.append("")
        if a.effort_estimate:
            lines.append(f"**Effort Estimate:** {a.effort_estimate}")
            lines.append("")
        lines.append("---")
        lines.append("")

    # User evaluations
    lines.append("## 👥 User Evaluations")
    lines.append("")
    for ue in result.user_evaluations:
        lines.append(f"### {ue.user_name} ({ue.persona_tag})")
        lines.append(f"**Favorite:** Approach {ue.favorite_id}")
        lines.append("")
        lines.append("| Approach | Rating | Would Use | Likes | Dislikes |")
        lines.append("|----------|--------|-----------|-------|----------|")
        for r in ue.reviews:
            would = "✅" if r.would_use else "❌"
            likes = r.likes.replace("|", "\\|").replace("\n", " ")
            dislikes = r.dislikes.replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {r.approach_id} | {r.rating}/10 | {would} | {likes} | {dislikes} |")
        lines.append("")
        lines.append(f"**Overall:** {ue.overall_thoughts}")
        lines.append("")

    # Discussion highlights
    if result.user_discussion:
        lines.append("## 💬 User Discussion Highlights")
        lines.append("")
        for msg in result.user_discussion:
            resp = (
                f" → @{msg.responding_to}"
                if msg.responding_to and msg.responding_to != "everyone"
                else ""
            )
            lines.append(f"**{msg.speaker}**{resp}: {msg.message}")
            lines.append("")

    # Analyst reports
    lines.append("## 📊 Analyst Reports")
    lines.append("")
    for ar in result.analyst_reports:
        lines.append(f"### {ar.analyst_name} ({ar.specialty})")
        lines.append(
            f"**Recommends:** Approach {ar.recommended_approach_id} "
            f"(Confidence: {ar.confidence:.0%})"
        )
        lines.append("")
        lines.append(f"{ar.analysis}")
        lines.append("")
        if ar.key_findings:
            lines.append("**Key Findings:**")
            for f in ar.key_findings:
                lines.append(f"- {f}")
            lines.append("")
        if ar.risks:
            lines.append("**Risks:**")
            for r in ar.risks:
                lines.append(f"- ⚠️ {r}")
            lines.append("")

    if result.analyst_discussion:
        lines.append("## Analyst Discussion")
        lines.append("")
        for msg in result.analyst_discussion:
            lines.extend([f"**{msg.speaker}** → {msg.responding_to}: {msg.message}", ""])

    return "\n".join(lines)
