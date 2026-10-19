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

## Kit self-adoption

The kit previously published the shared guidance without routing its own agents
to it or supplying a default GitHub PR template. Its root `AGENTS.md` now routes
PR preparation to the canonical process and default template; `CLAUDE.md`
continues to reach the same instructions. Kit verification uses the kit's Tests
section and the bundled review procedure and rubric.

The default GitHub template copies the canonical source, with a drift check in
the existing CI test glob. The source comment now refers to the process linked
from `AGENTS.md`, which works in the kit and adopting apps. Acceptance requires
both agents to reach the same process and the default template to match the
shared source. No sync-tool, application or automatic-publication changes are
needed. Restore the previous instructions and remove the default copy and
check to undo this self-adoption. Implementation is prepared locally; link the
PR here when published.
