# Security and privacy

## Data handling

Each user supplies their own provider credentials. Keys are passed to the configured
provider for authentication, not included as deliberation messages or result fields.
The application does not intentionally upload the user's environment, Git configuration,
local source tree, or credentials to GitHub. Public source does not give users access
to the maintainer's API account.

Problems and simulated panel feedback go to the user's configured LLM provider.
PNG, JPEG, and WebP screenshots supplied by the user are sent to that provider with the
initial planning request only (up to 3 images, 4 MiB each, 8 MiB total). The tool does not
write raw screenshots to disk; generated visual observations may appear in the returned
plan or report. Provider retention and billing policies apply. Crop or blur sensitive
content before sending screenshots.
MCP results go back to the connected host; optional Markdown and JSON reports contain
the problem and generated feedback. Provider and host retention policies apply.
This is not an offline or confidential-computing guarantee.

Use environment variables for keys. The ChatGPT desktop plugin can instead read a local
`.stuck-tool.json` file from its writable plugin-data directory. Its path is supplied by
the app and the file is outside the source checkout. Never put keys in plugin manifests.
Avoid `--api-key`: command arguments can appear in shell history and process listings.
Some LiteLLM versions automatically load local `.env` files. `.gitignore` excludes `.env`,
`.stuck-tool.json`, common credential files, logs, and the documented default reports;
other report filenames require review or should go in `reports/`.
Git ignore rules do not remove files that were already committed.

Our provider-error messages omit raw exception bodies, and configuration repr omits
the API key. Model-validation errors omit raw model output at CLI/MCP boundaries.
This does not prevent secrets from appearing if a user includes them in their problem,
enables third-party debug/callback logging, or shares reports. Third-party dependencies
still run with the user's process permissions; keep them updated.

The MCP server uses local stdio. The ChatGPT desktop plugin reads credentials only from
the local `.stuck-tool.json` in its plugin-data directory or from provider environment
variables; it does not send credentials in tool arguments. The deliberation agents
cannot execute code or read files. CLI report output writes to the paths explicitly
requested by the caller; only connect trusted MCP hosts and use a provider/base URL you
trust. Deep dive makes many provider calls and has no hard dollar spending cap.

## Reporting issues

After public hosting is configured, use the repository's **Security > Report a
vulnerability** feature when enabled. Do not include actual API keys, personal data,
or exploitable details in public issues. This project has no guaranteed response SLA.

If a real credential reaches a public repository, revoke or rotate it immediately.
Deleting a file or making the repository private does not reliably undo public exposure.
