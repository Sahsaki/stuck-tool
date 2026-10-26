"""
MCP (Model Context Protocol) server for stuck-tool.

Exposes stuck-tool as an MCP tool that any compatible AI assistant can use,
including Claude Code, Codex, Cursor, and more.

Usage:
    # Run the MCP server
    python -m stuck_tool.mcp_server

    # Or via the CLI
    stuck-tool-mcp

    # Add to Claude Code's MCP config:
    # {
    #   "mcpServers": {
    #     "stuck-tool": {
    #       "command": "python",
    #       "args": ["-m", "stuck_tool.mcp_server"]
    #     }
    #   }
    # }
"""

from __future__ import annotations

import asyncio
import logging
import sys

from pydantic import ValidationError

logger = logging.getLogger("stuck_tool.mcp")


def create_mcp_server():
    """Create and configure the MCP server with the stuck tool."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp.types import TextContent, Tool
    except ImportError:
        print(
            "Error: MCP dependencies not installed.\nInstall with: pip install stuck-tool[mcp]",
            file=sys.stderr,
        )
        sys.exit(1)

    from stuck_tool.core import StuckEngine
    from stuck_tool.display import format_result_markdown
    from stuck_tool.images import MAX_BASE64_CHARS, MAX_IMAGES, decode_mcp_images
    from stuck_tool.llm import LLMConfig
    from stuck_tool.personas import MODES

    server = Server("stuck-tool")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="stuck",
                description=(
                    "Multi-agent deliberation engine for when you're stuck on a problem. "
                    "Can inspect up to 3 PNG, JPEG, or WebP screenshots when passed in "
                    "the images argument; the configured model must support vision. "
                    "First analyzes the situation to design relevant approaches, simulated "
                    "users, and analyst specialties. Full/quick/express explore 10 approaches; "
                    "deepdive explores 20 with 20 users and 10 analysts. "
                    "The report states proposed changes and asks whether the user wants to "
                    "implement them; this tool does not modify files. "
                    "Use this when you or the user is stuck, unhappy with a solution, "
                    "facing a difficult architectural decision, or wants multiple "
                    "perspectives on a problem."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "problem": {
                            "type": "string",
                            "description": (
                                "Description of the problem you're stuck on. "
                                "Be as specific as possible — include context, "
                                "constraints, what you've already tried, and why "
                                "you're not happy with current approaches."
                            ),
                        },
                        "images": {
                            "type": "array",
                            "maxItems": MAX_IMAGES,
                            "description": (
                                "Optional screenshots sent to the configured vision model "
                                "during planning only. Each item has a MIME type and base64 data."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "mime_type": {
                                        "type": "string",
                                        "enum": ["image/png", "image/jpeg", "image/webp"],
                                    },
                                    "data": {
                                        "type": "string",
                                        "maxLength": MAX_BASE64_CHARS,
                                        "description": "Base64-encoded image bytes, not a URL.",
                                    },
                                },
                                "required": ["mime_type", "data"],
                                "additionalProperties": False,
                            },
                        },
                        "mode": {
                            "type": "string",
                            "enum": list(MODES),
                            "default": "quick",
                            "description": (
                                "Deliberation depth. "
                                "'full': 54 planned calls. "
                                "'quick': 15 planned calls, fewer agents. "
                                "'express': 6 planned calls, no discussion. "
                                "'deepdive': 138 planned calls, larger panel. Retries add calls."
                            ),
                        },
                        "model": {
                            "type": "string",
                            "default": "",
                            "description": (
                                "LLM model to use for the subagents. "
                                "Leave empty to auto-detect from environment. "
                                "Examples: 'gpt-4o', 'anthropic/claude-sonnet-4-20250514', "
                                "'ollama/llama3.1'"
                            ),
                        },
                        "full_report": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "Include full transcripts; default is a compact recommendation."
                            ),
                        },
                    },
                    "required": ["problem"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name != "stuck":
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        problem = arguments.get("problem", "")
        mode = arguments.get("mode", "quick")
        model = arguments.get("model", "")
        full_report = arguments.get("full_report", False)

        if not isinstance(problem, str) or not problem.strip():
            return [
                TextContent(
                    type="text",
                    text="Error: 'problem' is required. Describe what you're stuck on.",
                )
            ]

        if not isinstance(mode, str) or mode not in MODES:
            return [TextContent(type="text", text="Error: unknown mode")]
        if not isinstance(model, str) or not isinstance(full_report, bool):
            return [TextContent(type="text", text="Error: invalid model or full_report")]
        try:
            images = decode_mcp_images(arguments.get("images", []))
        except ValueError as e:
            return [TextContent(type="text", text=f"Error: {e}")]

        try:
            config = LLMConfig(model=model)
            engine = StuckEngine(
                llm_config=config,
                mode=mode,
                quiet=True,  # No terminal output in MCP mode
            )
            run = engine.run(problem, images=images) if images else engine.run(problem)
            result = await run
            report = format_result_markdown(result, full=full_report)

            return [TextContent(type="text", text=report)]

        except Exception as e:
            logger.error("stuck-tool failed (%s)", type(e).__name__)
            detail = (
                "Model output failed validation; response details omitted for privacy."
                if isinstance(e, ValidationError)
                else str(e)
            )
            return [
                TextContent(
                    type="text",
                    text=f"stuck-tool error: {detail}\n\nCheck your API key and model settings.",
                )
            ]

    return server, stdio_server


async def run_server():
    """Run the MCP server."""
    server, stdio_server_func = create_mcp_server()

    async with stdio_server_func() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    """Entry point for the MCP server."""
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
