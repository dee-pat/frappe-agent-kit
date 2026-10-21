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

## Pull requests

Before preparing or updating a PR, read the
[shared process](templates/pull-requests.md) and use the
[default PR template](.github/pull_request_template.md). These repository
instructions apply to both Codex and Claude Code through `CLAUDE.md`.
Use the Tests section below for kit verification and the bundled
[review procedure](skills/frappe-pr-review/SKILL.md) and
[report rubric](skills/frappe-pr-review/references/report.md) for self-review;
app runtime and framework checks apply when the change affects those areas.

The default template is a byte-identical copy of
`templates/pull_request_template.md`. Edit that shared source and refresh the
default copy together; `tools/test_pr_template.py` detects drift in CI.

## Tests

```bash
python3 tools/test_sync_skills.py
SEMGREP_BIN=<bench>/env/bin/semgrep python3 tools/test_semgrep_pr.py
semgrep --test --config semgrep/kit semgrep/kit/tests
python3 tools/test_deny_rules.py templates/codex.rules templates/claude-settings.json
python3 tools/test_workflow_concurrency.py templates/*.yml .github/workflows/*.yml
python3 tools/test_doc_links.py
```

`test_semgrep_pr.py` needs an absolute `SEMGREP_BIN` (or Semgrep on `PATH`) and
skips without Semgrep; a skip is not a pass. CI
(`.github/workflows/ci.yml`) pins Semgrep 1.172.0 and runs every
`tools/test_*.py`, the kit Semgrep rule tests and a parse of `templates/`.
The deny-rule and concurrency tests are copied into apps and default to app
paths, so the kit passes them the templates explicitly. The doc-link test is
copied into apps too and checks the kit's own guidance here.

## Commits

Conventional Commit titles: `feat:`, `fix:`, `docs:`, `ci:`, `test:`,
`refactor:`, `chore:`.

Like apps under `rules/frappe.md`, kit commits and pull requests carry no AI
attribution: no `Co-Authored-By` trailer for an AI agent and no "Generated
with ..." line.
