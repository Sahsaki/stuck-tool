# stuck-tool

Stuck? Convene a tiny committee of pretend experts. Get 10 approaches, a situation-matched
panel, and a roadmap. Works as a CLI, Python library, or MCP tool. MIT licensed.

The planner first identifies constraints, unknowns, and decision criteria. It then creates
distinct approach directions, simulated users with different priorities and temperaments,
and analysts with relevant specialties. A community garden problem gets a different panel
from a software architecture problem.

**These are simulated perspectives, not real user tests, measurements, or independent
research.** More agents do not guarantee a better answer. The tool proposes changes and asks
whether you want to implement them; it does not modify files or browse for evidence.

**[Install](#install)** · [Modes and cost](#modes-and-cost) · [Security](SECURITY.md)

## Install

Pick where you want to use it. Every setup that calls a model needs your own provider API
key; the provider bills those calls separately from Claude Code or ChatGPT subscriptions.

| Where | What you need | Setup guide |
| --- | --- | --- |
| Claude Code | Claude Code, `uv`, and a provider API key | [Claude Code steps](#claude-code-app) |
| ChatGPT desktop | ChatGPT desktop, `uv`, and a provider API key | [ChatGPT desktop steps](#chatgpt-desktop-app) |
| Terminal or Python | Python 3.10+ and a provider API key | [CLI and Python steps](#install-and-run) |
| Another MCP client | An MCP host, `uv`, and a provider API key | [MCP steps](#other-mcp-clients) |

## Install and run

Python 3.10+ is required. From a checkout:

```sh
python -m pip install -e ".[mcp]"
```

Set a provider key in your shell. For example, in PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-key"
stuck-tool --quick "Our onboarding loses people. We have one week and two developers."
```

In bash/zsh, use `export OPENAI_API_KEY="your-key"` instead. API calls use your configured
provider and can incur charges. This package does not provision credentials or subscription
access. Use `--model` or `STUCK_TOOL_MODEL` to select a model your provider supports.
Existing auto-detection chooses Anthropic if its key is present, then OpenAI, then local
Ollama if available. With only `STUCK_TOOL_API_KEY`, specify a matching model explicitly.

```sh
stuck-tool "How should we organize a community garden with limited volunteer time?"
stuck-tool --quick --output report.md --json-output result.json "Reconsider our onboarding"
stuck-tool --express "Which direction should we investigate first?"
stuck-deepdive "Reconsider our product strategy and the conflicting stakeholder needs"
stuck-tool --deepdive "The same deep dive through the main command"
python -m stuck_tool --help
```

Descriptions can also be piped through stdin. `stuck` is an alias for `stuck-tool`.
`--quiet` prints just the recommendation; Markdown/JSON exports still work.

## Modes and cost

| Mode | Approaches | Generator agents | Simulated users | Analysts including chief | Discussion rounds | Planned calls |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full (CLI/Python default) | 10 | 10 | 10 | 5 | 2 | 54 |
| Quick (MCP default) | 10 | 3 | 3 | 3 | 1 | 15 |
| Express | 10 | 1 | 2 | 2 | 0 | 6 |
| Deep dive | 20 | 20 | 20 | 10 | 3 | 138 |

Each mode includes one extra planning call. Quick mode batches the ten planned directions
across three generators; express batches them into one. Every simulated user reviews every
approach. Independent analyst reports are followed by a separate chief recommendation.
Discussion rounds apply to both users and independent analysts. Votes count the independent
reports plus the chief's choice; the chief can disagree with the majority, with reasons.

Quick mode makes about 72% fewer planned calls than full mode. This is **not a measured
token or dollar saving**: usage depends on the problem, model, response length, and retries.
Deep dive has substantially greater cost and is explicitly selected.

Token controls:

- Short, phase-specific output caps; responses must be JSON objects. Truncated or invalid
  responses stop the run rather than starting a paid repair loop.
- Compact review matrices preserve all ratings, likes, and dislikes without repeating
  field names for every review. Discussion prompts omit the full plans and replay only
  the previous round; complete transcripts remain in exports.
- At most two retries, only for transient provider failures; hidden LiteLLM retries are
  disabled. Other tasks in a failed phase are cancelled, though in-flight requests may
  already be billable.
- MCP returns a compact recommendation by default. Full reports are opt-in.
- JSON/Markdown reports expose provider-reported prompt/completion/total tokens, request
  counts including retries, and responses missing usage. Failed requests may incur usage
  that the provider does not report. No dollar estimates or hard spending cap are claimed.

`--rounds 0` skips discussions; `--rounds 0..3` overrides a mode's default. Planned calls:
`1 + generators + users + analysts + rounds * (users + analysts - 1)`.
`--max-concurrent 1..20` controls throughput, not token cost. Mode flags are mutually
exclusive. Python users can further lower `LLMConfig(max_tokens=...)`; too small a cap
can truncate structured responses. Input is limited to 20,000 characters, with an error
instead of silently dropping context.

## Claude Code app

Install [uv](https://docs.astral.sh/uv/) and Claude Code. Add this repository's plugin
marketplace, then install the plugin:

```sh
claude plugin marketplace add Sahsaki/stuck-tool
claude plugin install stuck-tool@stuck-tool
```

Set `STUCK_TOOL_API_KEY` and `STUCK_TOOL_MODEL` in the environment used to launch Claude
Code. For example, use `openai/gpt-4o` with an OpenAI API key or
`anthropic/claude-sonnet-4-20250514` with an Anthropic API key. Restart Claude Code after
changing environment variables. Claude Code subscriptions do not include provider API
usage; calls are billed by the provider.

## ChatGPT desktop app

The ChatGPT desktop app can load the local marketplace in this repository. Install
[uv](https://docs.astral.sh/uv/), clone the repository, open that checkout in the desktop
app, restart the app, then install `stuck-tool` from the Plugins Directory.

The plugin runs locally and needs your own model-provider API key. Create
`.stuck-tool.json` in the writable plugin-data directory supplied to the plugin MCP
server (`PLUGIN_DATA`) with your settings:

```json
{
  "model": "openai/gpt-4o",
  "api_key": "your-provider-api-key"
}
```

Use the matching model and key from the provider you choose. Keep this file private; it
is outside the source checkout and must never be committed. ChatGPT subscriptions do not
include provider API usage; calls are billed by the provider. The local marketplace is
for desktop use; submitting a local-stdio plugin to OpenAI's public directory requires
partner approval.

On a default desktop install, plugin data is under `~/.codex/plugins/data/agent-plugins/`
(Windows: `%USERPROFILE%\.codex\plugins\data\agent-plugins\`). Open the folder created
for this plugin and save `.stuck-tool.json` there; the host passes its exact path as
`PLUGIN_DATA` when it starts the server.

## Other MCP clients

Install `uv` and use the included `.mcp.json` as a starting point, or add a stdio server
entry using `uvx --from "stuck-tool[mcp] @ git+https://github.com/Sahsaki/stuck-tool.git"
stuck-tool-mcp`. Configure `STUCK_TOOL_API_KEY` and `STUCK_TOOL_MODEL` in the process
environment. This server uses local stdio; each MCP client has its own configuration
format.

The `stuck` tool accepts:

```json
{
  "problem": "What failed, what was tried, constraints, and desired outcome",
  "mode": "quick",
  "model": "",
  "full_report": false
}
```

Modes: `full`, `quick`, `express`, `deepdive`. Full reports include the chosen panel,
approaches, all reviews, both discussion transcripts, and the recommendation. The
compact response includes the roadmap, caveats, dissent, votes, and usage.

## Python

```python
import asyncio
from stuck_tool.core import run_stuck

result = asyncio.run(
    run_stuck("How should our garden organize volunteers?", mode="quick", quiet=True)
)
print(result.recommendation.summary)
print(result.usage)
```

`StuckEngine(LLMConfig(...), mode="deepdive")` exposes provider settings, including
custom API base, output cap, concurrency, timeout, and retries. Don't share an engine
between concurrent runs; create one per run for isolated statistics.

Environment variables: `STUCK_TOOL_MODEL`, `STUCK_TOOL_API_KEY`, `STUCK_TOOL_API_BASE`,
and the chosen provider's own key variables. Some LiteLLM versions also load `.env`
files automatically; treat them as local secrets and never upload them.
Inputs and simulated feedback are sent to your configured LLM provider. Reports contain
the supplied problem; review them for sensitive information before sharing.
Provider keys belong to each user: the public source contains no shared credentials.
See [SECURITY.md](SECURITY.md) for data handling and [PUBLISHING.md](PUBLISHING.md)
for a source-only GitHub upload that avoids local commit metadata.

## Develop and contribute

```sh
python -m pip install -e ".[dev,mcp]"
python -m pytest -q
python -m ruff check .
python -m build
```

Tests use mocked providers and do not need API keys. They check all four complete
pipelines, mode sizes and call counts, complete review coverage, feedback propagation,
votes, malformed output, cancellation, token accounting, CLI routing, and MCP integration.
See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution and release instructions.

