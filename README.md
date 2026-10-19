# Frappe agent kit

Agent guidance shared by Frappe Framework v16 apps: always-on rules for an
app's `AGENTS.md`, and skills that Codex and Claude Code load on demand. It adds
to [frappe/skills](https://github.com/frappe/skills) rather than replacing it:
pin `frappe-app-dev`, `code-style` and `frappe-code-review` from there, and
[frappe/semgrep-rules](https://github.com/frappe/semgrep-rules) for Semgrep.

## Contents

| Path                                 | What it is                                                                                        |
| ------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `rules/frappe.md`                    | Always-on Frappe rules: the few that agents get wrong by default, kept short to load every turn   |
| `skills/frappe-debugging/`           | Root-cause triage: classify, reproduce, localize, reduce, regression test first, fix, verify      |
| `skills/frappe-migration/`           | Expand/contract, renames, staged `unique`/`reqd`, patch retirement, and lifecycle fixture recipes |
| `skills/grilling/`                   | Interview the user one decision at a time before high-impact work                                 |
| `skills/pr-review-threads/`          | Resolve GitHub review conversations only after verifying the fix at the current head              |
| `skills/frappe-pr-review/`           | Evidence-based PR review: `frappe-code-review`, Semgrep and the installed framework, one report   |
| `skills/frappe-spa-client/`          | frappe-ui / Vue SPA calls to whitelisted methods: error mapping, CSRF, stale responses, Vitest    |
| `tools/sync-skills.sh`               | Vendor pinned skills, directories and the rules block into an app; check the copies match         |
| `tools/test_sync_skills.py`          | Regression tests for `sync-skills.sh`; run `python3 tools/test_sync_skills.py` after changing it  |
| `tools/semgrep-pr.sh`                | Report only the Frappe Semgrep findings a commit range introduces, without touching the checkout  |
| `tools/test_semgrep_pr.py`           | Tests for `semgrep-pr.sh`; need Semgrep (`SEMGREP_BIN=<bench>/env/bin/semgrep`)                   |
| `semgrep/kit/`                       | Kit Semgrep rules that enforce shared rules, with `semgrep --test` fixtures in `tests/`           |
| `templates/semgrep-pr.yml`           | Read-only, report-only GitHub Actions workflow that runs `semgrep-pr.sh` on pull requests         |
| `templates/claude-settings.json`     | Claude Code deny rules for site config reads and destructive or disclosing `bench` commands       |
| `templates/codex.rules`              | The matching Codex `prefix_rule` entries, each with `match` and `not_match` examples              |
| `templates/ci.yml`                   | Server and UI CI jobs on a fresh bench and test site, with a pinned `FRAPPE_VERSION`              |
| `templates/nightly.yml`              | Scheduled slow suites that report failures to one labelled issue and close it on recovery         |
| `templates/verification.md`          | Definition of done, verification evidence and a required-gates table for an app's docs            |
| `tools/test_deny_rules.py`           | Fails when a Codex deny prefix has no Claude Code deny rule; copied into apps                     |
| `tools/test_workflow_concurrency.py` | Checks a workflow cancels only superseded PR runs; copied into apps                               |
| `docs/pr-review.md`                  | Design, scope and progress of the PR-review setup                                                 |

Nothing here is app-specific. App rules, domain conventions, site names and
commands stay in each app's own `AGENTS.md`, and they win on conflict.

## Use in an app

Vendor plain files at a pinned revision. Symlinks and submodules break in CI,
fresh clones and hosted code review.

1. Copy `tools/sync-skills.sh` to the app's `scripts/`; its tests stay here. It
   expects the app at `<bench>/apps/<app>` and caches checkouts in
   `<bench>/.cache/agent-skills/`.
2. Add a `skills.lock` at the app root, one skill per line:

   ```text
   # name              repository               path                       revision (40 hex)  excludes
   frappe-app-dev      frappe/skills            skills/frappe-app-dev      <sha>              -
   frappe-code-review  frappe/skills            skills/frappe-code-review  <sha>              -
   frappe-migration    dee-pat/frappe-agent-kit skills/frappe-migration    <sha>              -
   frappe-pr-review    dee-pat/frappe-agent-kit skills/frappe-pr-review    <sha>              -
   ```

3. Run `scripts/sync-skills.sh sync` to copy each skill into `.agents/skills/`,
   then commit the lock and the copies together. `scripts/sync-skills.sh check`
   fails when a copy differs from its pin; run it in CI.
4. For Claude Code, link `.claude/skills` to `../.agents/skills`.
5. Embed the always-on rules: add this line to `skills.lock`

   ```text
   rule  dee-pat/frappe-agent-kit  rules/frappe.md  <sha>  AGENTS.md
   ```

   and put an empty marker pair where the block belongs in `AGENTS.md`:

   ```text
   <!-- BEGIN synced-rules: dee-pat/frappe-agent-kit/rules/frappe.md@<sha> -->
   <!-- END synced-rules: dee-pat/frappe-agent-kit/rules/frappe.md -->
   ```

   `sync` fills the block and `check` fails if anything between the markers
   differs from the pinned file. Text outside the markers is the app's own.

6. Vendor any other pinned upstream directory, such as Frappe's Semgrep rules,
   with a `vendor` line whose last column is a path inside the app:

   ```text
   vendor  frappe/semgrep-rules  rules  <sha>  semgrep/frappe
   ```

   `sync` replaces that path with the directory and `check` fails when it
   differs. Exclude the copy from the app's linters and scans.

7. For PR reviews, copy `tools/semgrep-pr.sh` to the app's `scripts/`. It
   scans a commit range against `semgrep/frappe/` in a temporary clone and
   reports only the findings the range introduces, so existing debt stays out
   of the review:

   ```bash
   scripts/semgrep-pr.sh origin/develop          # report only, exit 0
   scripts/semgrep-pr.sh --fail-on-new main HEAD # exit 1 on a new finding
   ```

   Keep any full-scan Semgrep gate the app has. Apps without a Semgrep CI job
   can copy `templates/semgrep-pr.yml` to `.github/workflows/`.

8. Vendor the kit's own Semgrep rules beside Frappe's:

   ```text
   vendor  dee-pat/frappe-agent-kit  semgrep/kit  <sha>  semgrep/kit
   ```

   `transactions.yml` bans `frappe.db.commit()` and `rollback()`, enforcing
   the shared rule. `finance.yml` bans `Decimal` built from a float literal;
   it is optional, for apps handling money or quantities; an app that does not
   want it leaves it out of `--config`. Run them as a blocking scan that
   excludes the vendored rules and their test fixtures:

   ```bash
   semgrep scan --error --metrics=off --severity ERROR \
     --config semgrep/kit/transactions.yml --config semgrep/kit/finance.yml \
     --exclude semgrep
   ```

## Shared PR process and template

`templates/pull-requests.md` and `templates/pull_request_template.md` are
canonical shared guidance, vendored without app-specific edits. The process
owns preparation and the four-section body; apps own commands, required gates,
domain rules and review overrides. Add both entries with the same full kit SHA
as the other kit pins:

```text
rule  dee-pat/frappe-agent-kit  templates/pull-requests.md  <sha>  docs/pull-requests.md
rule  dee-pat/frappe-agent-kit  templates/pull_request_template.md  <sha>  .github/pull_request_template.md
```

Create each target with the matching empty marker pair, for example:

```text
<!-- BEGIN synced-rules: dee-pat/frappe-agent-kit/templates/pull-requests.md@<sha> -->
<!-- END synced-rules: dee-pat/frappe-agent-kit/templates/pull-requests.md -->
```

Use `templates/pull_request_template.md` in the template's marker pair.
Then run `scripts/sync-skills.sh sync` and `check`. The existing `rule` mode
manages Markdown between HTML markers; it also works for these whole-file
copies without replacing neighboring GitHub workflows. Keep app overrides
outside the generated blocks or in the app's own guidance.

Adoption is opt-in: install both files when bumping the kit pin. Existing apps
without them keep their current PR format. The shared rule discovers the
process when present; the existing review rubric remains authoritative.

## Agent safety

The deny-rule templates protect local development benches from an agent that
reads site credentials or drops, restores or reconfigures a persistent site.
Production safety belongs to the hosting (for example Frappe Cloud), not to
these rules.

1. Copy `templates/claude-settings.json` to `.claude/settings.json` and
   `templates/codex.rules` to `.codex/rules/<app>.rules`, merging with any
   rules the app already has.
2. Replace `myapp` with the app's site prefix, so the rules name its
   persistent `-dev` and `-test` sites. Add any app-specific credential file
   to the `Read(...)` denies.
3. Copy `tools/test_deny_rules.py` to `scripts/`. From the app root,
   `python3 scripts/test_deny_rules.py` reads both files and fails when a
   Codex prefix has no Claude rule.
4. Run it in the app's lint gate, so the two files cannot drift.

## CI and verification templates

`templates/ci.yml`, `templates/nightly.yml` and `templates/verification.md`
are copied once and then owned by the app; they are not vendored or checked by
`sync-skills.sh`. Replace `myapp`, fill in the app's test and seed steps, and
copy `tools/test_workflow_concurrency.py` to `scripts/` to keep the CI
concurrency contract under test.

## Lint

Apps should cap complexity and keep unused imports out with ruff, matching the
shared rule on complexity:

```toml
[tool.ruff.lint]
select = ["F", "E", "W", "I", "UP", "B", "RUF", "C90"]  # with the app's own

[tool.ruff.lint.mccabe]
max-complexity = 15

[tool.ruff.lint.per-file-ignores]
"**/__init__.py" = ["F401"]
"<app>/hooks.py" = ["F401"]
```

Keep F401 enabled everywhere else. A deliberate re-export elsewhere carries
`# noqa: F401 -- <reason>`.

## Review a PR

With `frappe-pr-review` vendored, ask either agent in the app's checkout:

- Claude Code: `/frappe-pr-review 123`, or "review PR 123 with frappe-pr-review".
- Codex: `$frappe-pr-review 123`, or the same request in plain words.

The skill pins the range, reads the intent, applies `frappe-code-review`, runs
`semgrep-pr.sh`, checks framework behaviour in `<bench>/apps/frappe`, verifies
each finding and writes one report in the format of
[report.md](skills/frappe-pr-review/references/report.md). It does not fix,
commit, approve or post comments unless asked.

To upgrade, change the revision in `skills.lock`, run `sync`, and review the
diff before committing. Never edit a vendored copy; put adaptations in the
app's `AGENTS.md`.

## License

[MIT](LICENSE)
