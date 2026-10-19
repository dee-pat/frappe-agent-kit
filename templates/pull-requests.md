# Shared pull request process

Codex and Claude Code follow the same process and PR body format. The app's
instructions, verification requirements and review overrides take precedence.
Use the repository PR template rather than a personal default.

## Process

1. Read the applicable repository instructions and define the intended user
   outcome. Keep specs and progress notes proportional to the work; put run
   evidence in the PR or handoff.
2. Implement the smallest complete change, preserving unrelated work. Prove
   changed behavior and review affected domain documentation as the app requires.
3. Inspect the scoped diff, confirm the intended remote and base branch, and
   run the app's applicable gates. Record observed command results and reasons
   for checks not run.
4. Self-review the final diff using `frappe-pr-review` and the app's review
   contract. Distinguish self-review from independent review. Address blocking
   findings before claiming readiness.
5. Prepare the PR using the repository template. Commit, push and publish only
   within the user's authorization. Keep required CI pending until it completes
   on the published head; refresh the body after fixes.
6. Publish authorized review reports using the app's review contract. If a
   native review surface restricts output, put the full report in an authorized
   companion comment and link the native review and its reviewed revision.

When verification or publication is blocked, preserve the prepared work and
report the exact blocker and remaining action. After code changes, refresh
verification and review for the new revision; label retained evidence with
its original revision.

## PR body

Use these sections in order:

- **Summary:** the concrete problem and resulting behavior. Include a small
  before/after example or diagram when it helps assess the change.
- **Verification:** a compact command/result table, meaningful behavior
  evidence, CI links and exact revision, plus the app's required evidence.
  Distinguish passed, failed, pending, blocked and not applicable.
- **Risk and rollback:** affected users or flows, compatibility and migration
  effects, and the actual recovery path. Explain recovery requiring more than
  a code revert.
- **Review status:** readiness score and rationale, exact reviewed head/base,
  self or independent review, report link when available, and remaining
  findings. Use `frappe-pr-review`'s report rubric and app overrides. This
  summary supplements the full review report and any required fix prompt.

Keep simple changes brief. Include screenshots or a GIF for visible changes
when useful, and line counts only when they substantiate a stated goal.
Replace template prompts with facts or explicit pending/not-applicable status.
