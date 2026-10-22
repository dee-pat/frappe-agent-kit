# __APP_TITLE__ agent guidance

Read this file from both Codex and Claude Code. Use local skills under
`.agents/skills/`. Pinned upstream copies and the shared rules below are managed
through skills.lock; keep app-specific changes outside generated blocks.

## Read by task

| Task | Read first | Then, only if |
| --- | --- | --- |
| Pushing or merging | [Merge safeguards](docs/merge-safeguards.md) | |
| Running gates | [Verification](docs/verification.md) | |
| Frappe implementation | `frappe-app-dev`, `code-style` | SPA calls: `frappe-spa-client` |
| Schema or patch changes | `frappe-migration` | |
| Failing tests or builds | `frappe-debugging` | |
| PR or diff review | `frappe-pr-review` | Review conversations: `pr-review-threads` |
| Unsettled business rules | `grilling` | |

## Local workflow

- Keep the GitHub repository private.
- Install the local push guard with `scripts/install-hooks.sh` in every clone.
  Push feature branches; changes to main go through a PR.
- When a merge is authorized, use `python3 scripts/merge-pr.py <number>`.
  It validates current PR checks, syncs main, cleans up eligible branches and
  verifies CI on the merge commit. Use `--resume` after a partial handoff.
- Preserve branches containing unmerged work or used by other worktrees.
- The app package is `__APP_NAME__/`; the Frappe module is
  `__APP_NAME__/__MODULE_NAME__/`.
- Run bench commands from the bench root with the explicit target site.
  Interactive work uses __DEV_SITE__; automated tests use __TEST_SITE__.
- Preserve both persistent sites and site configuration credentials. Codex and
  Claude protection rules name the same sites; update both together.
- Keep vendored skills, scripts and Semgrep rules identical to their pins;
  put app adaptations here and exclude vendored copies from formatters.
- Before preparing a PR, read [the shared process](docs/pull-requests.md).

<!-- BEGIN synced-rules: dee-pat/frappe-agent-kit/rules/frappe.md@__KIT_REVISION__ -->
<!-- END synced-rules: dee-pat/frappe-agent-kit/rules/frappe.md -->
