# Private app bootstrap

## Goal and scope

Create a private Frappe v16 app with isolated development/test sites, pinned
agent guidance, CI, local push protection and a complete guarded PR merge
handoff. Use the established model app workflow as the reference without
embedding its app, repository or site names in generated projects.

## Design and contract

A JSON configuration supplies metadata, GitHub ownership and the bench path.
Version defaults are exact pins; the kit itself is pinned to the clean Git
revision containing the bootstrap tool. Commands run without a shell. Passwords
come from named environment variables, never from JSON or the resume journal.
The tool can initialize a missing bench but requires an installed database
server, Node/Yarn, Redis binaries, Git, GitHub CLI authentication and Python.

Phases initialize the bench, scaffold the app, install isolated sites, create
an empty private repository, generate setup on a feature branch, validate it,
open the setup PR and execute the complete guarded merge workflow. Initial
scaffold main is published before installing the main-push hook. All later
changes use a PR. No existing repository is made public or adopted implicitly.

Dry-run validates configuration and prints the phase plan without contacting
GitHub or creating files. Resume requires the identical resolved configuration
and a journal owned by this bootstrap. A per-bench lock prevents concurrent
runs. Resource conflicts and user edits fail closed. App state is outside the
app repository and each phase checkpoint is written atomically.

## Failure and recovery

No sites, apps or repositories are dropped, restored or overwritten. A failure
preserves the journal and reports the incomplete phase. Completed phases are
revalidated; partial operations reconcile owned resources where safe. Ambiguous
ownership, changed inputs or changed generated files require manual inspection.
If a PR is merged, resume completes the handoff rather than merging again.
API errors and unsuccessful CI stop the run. Secrets are redacted from errors.

## Acceptance and progress

Implementation is complete; publication and review are tracked in
[PR #16](https://github.com/dee-pat/frappe-agent-kit/pull/16).
Acceptance requires command/state tests for
dry-run isolation, pin validation, conflicts, partial failures, resume, secret
redaction and private-only publication. Generated projects must include the
three CI jobs and tested merge safeguards, with no reference-project names.
All kit tool, template and Semgrep gates must pass. A real external bootstrap
is outside validation scope; no live app/site/repository is created by tests.

## Usage

Run from a clean checkout of a **published full kit commit** containing this
command. The default kit pin is that checkout's HEAD; apply checks that GitHub
can resolve it before creating resources. Overrides must be full commit SHAs or
exact versions. The tool uses its own isolated, pinned Bench CLI environment.
It does not install or reconfigure the machine's database server or Node.

Create a non-secret JSON file based on [the example](../templates/private-app-config.json),
then run:

```bash
python3 tools/bootstrap-private-app.py --config /absolute/path/app.json --dry-run
# Set FRAPPE_BOOTSTRAP_ADMIN_PASSWORD in the environment through your secret manager.
# Optionally set FRAPPE_BOOTSTRAP_DB_ROOT_PASSWORD for local database authentication.
python3 tools/bootstrap-private-app.py --config /absolute/path/app.json
python3 tools/bootstrap-private-app.py --config /absolute/path/app.json --resume
```

A normal apply creates sites and a private GitHub repository, commits and pushes
the app, opens a setup PR, and merges only after the required checks succeed.
Treat invocation as authorization for those operations. Dry-run does none of
those operations and does not require passwords or GitHub authentication.
Existing apps, sites and repositories are refused; this tool is not an adoption
or migration tool. Bench reuse requires a clean Frappe checkout at the pinned tag.

The defaults in [versions.json](../tools/private_app_bootstrap/versions.json)
currently pin Python 3.14.6, Node 24.18.0, Frappe v16.51.0, Bench 5.31.0,
pre-commit 4.3.0 and Semgrep 1.172.0, plus full upstream skills/rules SHAs.
Yarn 1.22.22 and a reachable MariaDB server compatible with Frappe v16 are
prerequisites. Redis binaries must be available; existing responding local
services are reused, otherwise the bench's configured services are started.
GitHub authentication needs permission to create private repositories, push
workflow files, read Actions and merge PRs for the selected owner.

Journal files live under the bench parent's `.frappe-bootstrap/` directory,
outside the app repository, with private permissions. They record resolved
pins, phase checkpoints, resource identities and generated-file hashes, never
password values. Keep the same config and pinned kit checkout for resume. A
crash after GitHub creates a repository but before its identity is journaled
requires manual inspection: the tool will not guess ownership or adopt it.
Incomplete bench or site initialization may also need manual repair; resume
never recreates or forcibly replaces a partially initialized resource.

The generated app includes an isolated test site, a real installation smoke
test, immutable agent kit pins, the Lint/Agent kit/Server CI jobs, Codex/Claude
guidance and the tested merge workflow. Branch protection still depends on the
GitHub account plan; local safeguards are not server-side enforcement. Codex
project registration remains manual because no supported creation API exists.
