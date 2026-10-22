# Private repository merge safeguards

## Goal and usage

Keep the repository private and route changes through a PR with successful
Lint, Agent kit and Server checks. GitHub Free cannot enforce these rules for
private repositories; these local safeguards prevent routine mistakes and can
be bypassed through another checkout or GitHub's UI.

Install the hook once in each clone with `scripts/install-hooks.sh`. It rejects
all updates to refs/heads/main, including deletion, force pushes and updates
from differently named local branches. Existing conflicting hooks are preserved.

After the user authorizes a merge:

```bash
python3 scripts/merge-pr.py 123 --check-only
python3 scripts/merge-pr.py 123
```

The script requires an open non-draft PR to main, a branch containing current
main, and successful required checks from GitHub Actions on the exact PR head.
It also requires a clean checkout and matching origin fetch/push repositories.
Check-only performs no merge, checkout sync, branch deletion or CI waiting.

## Complete handoff

After the confirmed merge, the script fast-forwards local main, deletes only
safely merged PR branches and waits for push-triggered main CI on the exact
merge commit. It checks private visibility before and after the operation.
`--ci-timeout` sets the bounded wait in seconds (default 1800).

Cleanup is restricted to this repository's PR branch. Each tip must be merged
into main. Branches with unmerged work or another worktree are preserved; main
is never deleted. Remote deletion uses an explicit expected-tip lease to protect
concurrent pushes. Already absent branches are complete. No forced local
deletion or reset is used.

## Failure and recovery

Preflight failures prevent merging. After a confirmed merge, sync, cleanup or
CI failures return nonzero and clearly report the merged state. Fix the cause
and retry `python3 scripts/merge-pr.py 123 --resume`; it never merges again.
A failed main CI run leaves the merge intact and requires follow-up.
GitHub Free does not atomically enforce base/check state between validation and
merging; local hooks do not replace server-side branch protection.
