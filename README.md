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

## MCP integration

Install the `mcp` extra first. For clients using JSON MCP configuration:

```json
{
  "mcpServers": {
    "stuck-tool": {
      "command": "python",
      "args": ["-m", "stuck_tool.mcp_server"]
    }
  }
}
```

Use the interpreter from the environment where you installed the package. The server
inherits provider environment variables from its host. `stuck-tool-mcp` is an equivalent
server entry point. Clients use their own configuration formats; the JSON above is not
a universal config file.

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

