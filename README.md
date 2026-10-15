# Frappe agent kit

Agent guidance shared by Frappe Framework v16 apps: always-on rules for an
app's `AGENTS.md`, and skills that Codex and Claude Code load on demand. It adds
to [frappe/skills](https://github.com/frappe/skills) rather than replacing it:
pin `frappe-app-dev`, `code-style` and `frappe-code-review` from there.

## Contents

| Path                        | What it is                                                                                           |
| --------------------------- | ---------------------------------------------------------------------------------------------------- |
| `rules/frappe.md`           | Always-on Frappe rules: the few that agents get wrong by default, kept short to load every turn       |
| `skills/frappe-migration/`  | Expand/contract, renames, staged `unique`/`reqd`, patch retirement, and lifecycle fixture recipes     |
| `skills/grilling/`          | Interview the user one decision at a time before high-impact work                                     |
| `skills/pr-review-threads/` | Resolve GitHub review conversations only after verifying the fix at the current head                 |
| `tools/sync-skills.sh`      | Vendor pinned skills and the rules block into an app, and check that the copies have not drifted     |

Nothing here is app-specific. App rules, domain conventions, site names and
commands stay in each app's own `AGENTS.md`, and they win on conflict.

## Use in an app

Vendor plain files at a pinned revision. Symlinks and submodules break in CI,
fresh clones and hosted code review.

1. Copy `tools/sync-skills.sh` (and, to run its regression tests, `tools/test_sync_skills.py`) to the app's `scripts/`. It expects the app at
   `<bench>/apps/<app>` and caches checkouts in `<bench>/.cache/agent-skills/`.
2. Add a `skills.lock` at the app root, one skill per line:

   ```text
   # name              repository               path                       revision (40 hex)  excludes
   frappe-app-dev      frappe/skills            skills/frappe-app-dev      <sha>              -
   frappe-migration    dee-pat/frappe-agent-kit skills/frappe-migration    <sha>              -
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

To upgrade, change the revision in `skills.lock`, run `sync`, and review the
diff before committing. Never edit a vendored copy; put adaptations in the
app's `AGENTS.md`.

## License

[MIT](LICENSE)
