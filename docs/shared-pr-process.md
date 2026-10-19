# Shared PR guidance: spec and progress

## Goal and scope

Give Codex and Claude Code one PR preparation process and report structure.
Keep app commands, domain rules and verification gates in app guidance. No
runtime, data, permission, review-scoring or automatic publication changes.

## Design and compatibility

Canonical process and template live in `templates/`. Apps pin both with the
existing `rule` lock entry and sync them into `docs/pull-requests.md` and
`.github/pull_request_template.md`. HTML markers identify the source revision;
`check` detects drift. App overrides stay outside the generated blocks.
The always-on rule routes PR preparation to the process only when installed,
so a pin bump without adoption preserves an app's current workflow.

## Failure and recovery

Failed fetches leave no valid cache entry. Restore the previous pin and sync
to recover previous shared guidance. Initial adoption adds marker pairs before
sync; keep unrelated target content outside the blocks. Publication remains
subject to user authorization.

## Acceptance and rollout

- Both agents discover the shared process through the generated rule block.
- Process and template sync and check against the same immutable kit revision.
- App-specific gates and review overrides remain authoritative.
- Existing sync regression tests and app documentation checks cover adoption;
  no sync-tool change or new dependency is required.

## Progress

Canonical files, discovery rule and sync coverage are implemented in
[PR #12](https://github.com/dee-pat/frappe-agent-kit/pull/12). Pinned adoption
is prepared; CI and review status live on the PR. Validate the next PR from
each agent for adherence before adding enforcement.
