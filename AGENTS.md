# Frappe agent kit

Shared agent guidance for Frappe v16 apps: always-on rules, skills, Semgrep
rules and the tools that vendor them. `CLAUDE.md` is a symlink to this file.

## Rules

- Nothing here is app-specific. No app names, DocTypes, domain terms, site
  names or commands; those stay in each app's own `AGENTS.md`. Examples use
  neutral names.
- Apps vendor this repository at a pinned revision through `skills.lock`, so a
  wording change to a skill, rule or Semgrep rule reaches every app on its next
  pin bump. Treat it as a breaking change for anyone who pins: list each
  changed sentence or rule in the PR description.
- `rules/frappe.md` loads on every turn in every app. Keep it short; add a line
  only for a mistake agents make by default.
- Each tool's tests live beside it in `tools/test_*.py`. Change a tool and its
  tests together.

## Tests

```bash
python3 tools/test_sync_skills.py
SEMGREP_BIN=<bench>/env/bin/semgrep python3 tools/test_semgrep_pr.py
```

`test_semgrep_pr.py` needs an absolute `SEMGREP_BIN` (or Semgrep on `PATH`) and
skips without Semgrep; a skip is not a pass. CI
(`.github/workflows/ci.yml`) pins Semgrep 1.172.0 and runs every
`tools/test_*.py` and a parse of `templates/`.

## Commits

Conventional Commit titles: `feat:`, `fix:`, `docs:`, `ci:`, `test:`,
`refactor:`, `chore:`.
