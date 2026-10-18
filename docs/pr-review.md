# Frappe PR review: spec and progress

## Goal

Codex and Claude Code review Frappe app changes the same way: grounded in the
installed framework source, Frappe's official review guidance and Frappe's
Semgrep rules, with one deduplicated, evidence-backed report. Both agents run on
their existing subscriptions; nothing here calls a model API.

## Non-goals

- No app business logic, and no app-specific review rules; apps keep those in
  their own `AGENTS.md` and review docs, which win on conflict.
- No copy of `frappe-code-review`, `frappe-app-dev` or Frappe's Semgrep rules.
  Apps pin them from upstream through `skills.lock`.
- No `ship-it`, `deep-app-audit` or community skill packages.
- No automatic fixes, commits, approvals or published comments.

## Design

| Piece                              | Owns                                                                                     |
| ---------------------------------- | ---------------------------------------------------------------------------------------- |
| `frappe-code-review` (frappe/skills) | What to look for: correctness, security, performance, concurrency, API design, tests    |
| `frappe/frappe` `code_review.md`   | Maintainers' review checklist, when the installed version ships it (v16 does not)        |
| `skills/frappe-pr-review/`         | The procedure: scope, evidence, Semgrep, framework source, verification, report format  |
| `tools/semgrep-pr.sh`              | Reproducible pattern checks; reports only findings the change introduces               |
| `templates/semgrep-pr.yml`         | Report-only PR workflow for apps without a Semgrep CI job                                |
| `rules/frappe.md`                  | One always-on line pointing to the skills and the installed framework source            |

`semgrep-pr.sh` scans the head commit in a temporary shared clone with
`--baseline-commit`, so it never touches the user's checkout and existing
findings (technical debt) stay out of the PR result. It exits 0 when it only
reports; `--fail-on-new` makes new findings fail, for apps that opt in.

## Consistency and safety rules

- Review is read-only by default; the skill never fixes, commits, pushes,
  approves or posts unless the user asks.
- PR code is untrusted: run it only on a disposable site; never against
  production data.
- The installed framework (`<bench>/apps/frappe`, at the version the bench
  runs) is the authority on behaviour; remembered behaviour is not evidence.

## Tests

`tools/test_semgrep_pr.py`: a new finding is reported, a pre-existing one is
not, the user's checkout and its uncommitted changes are untouched, and
`--fail-on-new` sets the exit status.

## Rollout

Apps add `frappe-pr-review` to `skills.lock` at the kit revision that ships it,
copy `tools/semgrep-pr.sh` to `scripts/`, and bump the `rule` line. Apps that
already block on a full Semgrep scan keep that job; the new tool adds the
PR-scoped view used by reviewers.

## Acceptance criteria

- Both agents discover `frappe-pr-review` from `.agents/skills/` (Codex) and
  `.claude/skills/` (Claude Code).
- `semgrep-pr.sh` runs with the bench's pinned Semgrep against the vendored
  Frappe rules and its tests pass.
- `rules/frappe.md` stays short and names when to use each skill.

## Progress

- 2026-10-16: skill, tool, tests, template and rule line added on
  `feat/frappe-pr-review`. Not yet adopted by any app.
- Validated against a throwaway clone of `bond_management`: `sync` and `check`
  vendored the skill and rule block; Claude Code listed `frappe-pr-review`
  beside the official skills; `semgrep-pr.sh` ran with Semgrep 1.172.0 and the
  pinned and latest Frappe rules (0 new findings over the last 30 commits).
  Codex CLI 0.163.0 (`gpt-6-luna`, read-only sandbox) also listed
  `frappe-pr-review` from `.agents/skills/`. The workflow template parses as
  YAML but has not run on GitHub.
- 2026-10-18: on `feat/ci-review-scoring-semgrep`, `report.md` gained the
  merge-readiness score and the blocking rule, generalized from
  `bond_management`'s review contract; the kit gained CI and its own Semgrep
  rules in `semgrep/kit/`.

## Follow-ups

- Adopt in `bond_management`: add the lock line, copy the tool, bump the kit
  pins, and consider bumping `frappe/semgrep-rules` from `de085539` to
  `81a6e3d4` (adds GET side-effect, `enqueue_after_commit` and
  `override_doctype_class` rules).
