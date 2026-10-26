"""
CLI interface for stuck-tool.

Usage:
    stuck-tool "I can't decide between REST and GraphQL for my API"
    stuck-tool --model gpt-4o --rounds 3 "My auth system is too complex"
    stuck-tool --quick "How should I structure my database?"
    stuck-tool --output report.md "Performance is terrible"
    echo "My problem..." | stuck-tool
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from pydantic import ValidationError

from stuck_tool import __version__
from stuck_tool.core import StuckEngine
from stuck_tool.display import console, format_result_markdown, print_final_result
from stuck_tool.images import MAX_IMAGES, load_image
from stuck_tool.llm import LLMConfig

HELP_EPILOG = """
\b
Examples:
  stuck-tool "I can't decide between REST and GraphQL"
  stuck-tool --model gpt-4o "My auth system is too complex"
  stuck-tool --quick "How should I structure my database?"
  stuck-tool --output report.md "Performance is terrible"
  stuck-tool --image screenshot.png "Why does this Roblox menu look wrong?"
  cat problem.txt | stuck-tool
  stuck-tool --express "Which framework should I use?"
  stuck-deepdive "Reconsider our entire product strategy"

\b
Environment Variables:
  STUCK_TOOL_MODEL      Default LLM model
  STUCK_TOOL_API_KEY    API key for the LLM provider
  STUCK_TOOL_API_BASE   Custom API base URL (for Ollama, etc.)
  ANTHROPIC_API_KEY     Anthropic API key
  OPENAI_API_KEY        OpenAI API key

\b
Modes:
  (default)   10 approaches, 10 users, 5 analysts (54 planned calls)
  --quick     10 approaches, 3 users, 3 analysts (15 planned calls)
  --express   10 approaches, 2 users, 2 analysts (6 planned calls)
  --deepdive  20 approaches, 20 users, 10 analysts (138 planned calls)
  Calls exclude retries. All panel roles adapt to your situation.
"""


@click.command(epilog=HELP_EPILOG)
@click.argument("problem", required=False)
@click.option(
    "--model",
    "-m",
    default="",
    help="LLM model to use (auto-detected from env if not set).",
)
@click.option(
    "--api-key",
    "-k",
    default="",
    help="API key for the LLM provider.",
)
@click.option(
    "--api-base",
    default="",
    help="Custom API base URL (e.g., http://localhost:11434 for Ollama).",
)
@click.option(
    "--rounds",
    "-r",
    default=None,
    type=click.IntRange(0, 3),
    help="Override discussion rounds (0-3); otherwise use the mode default.",
)
@click.option(
    "--quick",
    "-q",
    is_flag=True,
    help="Quick mode: fewer agents, all 10 approaches, 1 discussion round.",
)
@click.option(
    "--express",
    "-e",
    is_flag=True,
    help="Express mode: skip discussions entirely.",
)
@click.option(
    "--deepdive", is_flag=True, help="Larger panel: 20 approaches, 20 users, 10 analysts."
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Save full report to a markdown file.",
)
@click.option(
    "--image",
    "image_paths",
    type=click.Path(path_type=Path),
    multiple=True,
    help="Attach a PNG, JPEG, or WebP screenshot (up to 3).",
)
@click.option(
    "--json-output",
    "-j",
    type=click.Path(),
    help="Save raw results as JSON.",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Suppress progress output (useful for piping).",
)
@click.option(
    "--max-concurrent",
    "-c",
    default=10,
    type=click.IntRange(1, 20),
    help="Max concurrent LLM calls (default: 10).",
)
@click.option(
    "--temperature",
    "-t",
    default=0.9,
    type=click.FloatRange(0, 2),
    help="Base temperature for LLM calls (default: 0.9).",
)
@click.version_option(version=__version__, prog_name="stuck-tool")
def main(
    problem: str | None,
    model: str,
    api_key: str,
    api_base: str,
    rounds: int | None,
    quick: bool,
    express: bool,
    deepdive: bool,
    output: str | None,
    image_paths: tuple[Path, ...],
    json_output: str | None,
    quiet: bool,
    max_concurrent: int,
    temperature: float,
):
    """stuck-tool — Situation-specific agents explore, evaluate, and recommend.

    Pass your problem as an argument or pipe it via stdin.
    """
    # Read from stdin if no argument provided
    if not problem:
        if not sys.stdin.isatty():
            problem = sys.stdin.read().strip()
        else:
            console.print("[red]Error:[/] Please provide a problem description.")
            console.print()
            console.print('Usage: stuck-tool "Your problem description here"')
            console.print('   or: echo "Your problem" | stuck-tool')
            console.print("   or: stuck-tool --help")
            sys.exit(1)

    if not problem:
        console.print("[red]Error:[/] Empty problem description.")
        sys.exit(1)

    if sum((quick, express, deepdive)) > 1:
        raise click.UsageError("Choose only one of --quick, --express, and --deepdive")
    mode = "deepdive" if deepdive else "express" if express else "quick" if quick else "full"
    if len(image_paths) > MAX_IMAGES:
        raise click.BadParameter(f"provide no more than {MAX_IMAGES} images", param_hint="--image")

    llm_config = None
    try:
        images = [load_image(path) for path in image_paths]
        llm_config = LLMConfig(
            model=model,
            api_key=api_key,
            api_base=api_base,
            max_concurrent=max_concurrent,
            temperature=temperature,
        )
        engine = StuckEngine(
            llm_config=llm_config,
            discussion_rounds=rounds,
            quiet=quiet,
            mode=mode,
        )
        run = engine.run(problem, images=images) if images else engine.run(problem)
        result = asyncio.run(run)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/]")
        sys.exit(130)
    except Exception as e:
        detail = (
            "Model output failed validation; response details omitted for privacy."
            if isinstance(e, ValidationError)
            else str(e)
        )
        console.print(f"\nError: {detail}", markup=False)
        if not quiet:
            console.print("[dim]Tip: Check your API key and model settings.[/]")
        sys.exit(1)

    # Display results
    if not quiet:
        print_final_result(result)

    # Save markdown report
    if output:
        report = format_result_markdown(result)
        with open(output, "w", encoding="utf-8") as f:
            f.write(report)
        if not quiet:
            console.print(f"\n  [green]📄 Report saved to:[/] {output}")

    # Save JSON
    if json_output:
        with open(json_output, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        if not quiet:
            console.print(f"  [green]📦 JSON saved to:[/] {json_output}")

    # If quiet mode, output the recommendation to stdout
    if quiet:
        rec = result.recommendation
        winning = next(a for a in result.approaches if a.id == rec.winning_approach_id)
        click.echo(f"RECOMMENDATION: Approach {winning.id} — {winning.name}")
        click.echo(f"CONSENSUS: {rec.consensus_level}")
        click.echo(f"SUMMARY: {rec.summary}")
        click.echo(f"PROPOSED CHANGES: {rec.implementation_roadmap}")
        click.echo("Want to implement these proposed changes? This tool hasn't changed any files.")


if __name__ == "__main__":
    main()


def deepdive():
    """The stuck-deepdive command shares every option with stuck-tool."""
    main.main(args=["--deepdive", *sys.argv[1:]], prog_name="stuck-deepdive")
