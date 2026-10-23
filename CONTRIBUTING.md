# Contributing

Install Python 3.10+ and run the development commands in the README. Keep changes small,
include a mocked regression test for behavior changes, and run pytest and Ruff before
submitting a pull request. Avoid paid provider calls in CI. Contributions are MIT licensed.

For bugs, include the mode, Python version, package version, and a minimal redacted
reproduction. Never include credentials or private problem descriptions. If reporting a
security issue, use the hosting repository's private vulnerability reporting feature
when enabled; do not post exploitable details publicly.

## Release checklist

1. Run tests, lint, and `python -m build`. Smoke-test the built wheel and MCP connection.
2. Manually test one small problem with your chosen provider and record the model and
   usage. Mocked tests validate orchestration, not the quality of real model decisions.
3. Review tracked files for secrets and personal data. Keep the MIT license. Create a
   public repository under your own account; add its actual URLs to `pyproject.toml`.
4. Push the source and confirm CI passes. Enable private vulnerability reporting and
   maintain issues and releases. Publish to PyPI only after checking name availability
   and configuring package ownership; the distribution name here is not a reservation.
5. Share useful examples and collect real feedback. An OSS support application should
   reflect actual adoption and maintenance, without invented stars, users, or outcomes.
