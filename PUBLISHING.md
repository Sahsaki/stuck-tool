# Upload to GitHub without local metadata

Use a source-only archive, not the full development folder. A source-only archive omits
`.git`, environments, caches, logs, credentials, reports, and generated package artifacts.
GitHub will still associate a public repository with your account and public profile.

1. Open [GitHub email settings](https://github.com/settings/emails). Enable **Keep my
   email addresses private** and **Block command line pushes that expose my email**.
   Review your public profile name, bio, and location before creating a public project.
2. Extract the reviewed source archive into a new folder. In that folder, check that
   `.github`, `.agents`, `.claude-plugin`, `stuck_tool`, and `tests` are present alongside
   `.gitignore`, `.mcp.json`, `mcp.json`, `plugin.json`, the Markdown docs, `LICENSE`, and
   `pyproject.toml`. Do not add anything from your development folder.
3. Open [New repository](https://github.com/new), name it `stuck-tool`, and start with
   **Private** visibility. Leave the README, license, and gitignore initialization empty
   because the source already includes them.
4. Use the empty repository's **uploading an existing file** link, or **Add file > Upload
   files**. Drag the extracted folder's contents, including the three subfolders, into
   the upload area. Upload the contents, not the ZIP and not an extra enclosing folder.
   Confirm the preview includes `.github/workflows/ci.yml` and `.gitignore`, then commit.
5. Review the files and commit identity on GitHub. Once satisfied, change visibility to
   **Public** in repository settings. Enable available secret scanning/push protection,
   Dependabot alerts/security updates, and private vulnerability reporting. Confirm CI
   passes before promoting it to users.

For future command-line commits, copy your exact GitHub `noreply` address from email
settings and set it for this repository before committing:

```sh
git config --local user.name "YOUR_PUBLIC_GITHUB_USERNAME"
git config --local user.email "YOUR_GITHUB_NOREPLY_ADDRESS"
```

Replace both placeholders. Your global Git identity stays unchanged. Git author names
and emails are stored in commits; do not create the first local commit until these are
set correctly. Never use `git add -f` to bypass ignored credential/report files.

See GitHub's [file upload instructions](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
and [email privacy instructions](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/blocking-command-line-pushes-that-expose-your-personal-email-address).
