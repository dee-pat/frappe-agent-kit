# Review report

One report per review. Keep it short enough to read in a minute; detail goes in
the findings, not in narration. The app's review contract may add fields (usage,
a fix prompt); include them where it says.

## Header

- **Reviewed:** `<base sha>..<head sha>` (PR link or branch), and the installed
  Frappe version used as reference. For a re-review, also the round number and
  the previously reviewed head.
- **Merge readiness:** `Merge readiness: N/5`, or `N/5 (provisional)`, with a
  one-line rationale; see _Merge readiness_ below.
- **Verdict:** changes requested when a blocking finding remains (see _When a
  finding blocks merge_); otherwise no blocking findings.
- **Checks:** each command you ran with its observed exit status (Semgrep,
  tests, linters), existing CI results cited as CI evidence, and checks not run
  with the reason.

## Findings

Order by severity, then by file. Each finding:

```markdown
### [P1] Customer can read another company's invoices

`app/api/billing.py:42-57`, confirmed

`get_invoices` passes `ignore_permissions=True` to `frappe.get_all`, so the
`permission_query_conditions` hook in `hooks.py` never runs for this endpoint.

- **When:** any logged-in user calls the method with another company's name.
- **Evidence:** `frappe/model/db_query.py:674` (v16.51.0) adds match
  conditions only when `ignore_permissions` is false; no other check guards the
  call path from `@frappe.whitelist()` at line 38.
- **Fix:** use `frappe.qb.get_query(..., ignore_permissions=False)` so the hook
  runs; add a test that a customer without a User Permission on the company
  gets no rows.
```

The example is illustrative; every path, line and version in a real finding
comes from code you read. An app's review contract may prefix each heading with
its own finding ID, for example `### F1 [P1] ...`.

- **Severity**
  - **P0:** broad, immediate harm: data exposure across tenants or users, data
    destroyed or silently corrupted, a critical flow broken for everyone.
  - **P1:** a security, money or data-loss defect below P0.
  - **P2:** a correctness defect or regression that must be fixed before merge,
    including a missing test for new risky behaviour.
  - **P3:** a real but minor defect worth fixing.

  An app may add domain examples of each priority in its own review docs; its
  examples win on conflict.
- **Location:** the file and line range in the head revision, on lines that are
  in the diff when the finding is about the change, so it maps to a GitHub
  inline comment. Use a file-level or PR-level note only when no line fits.
- **Status:** _confirmed_ (traced or reproduced) or _needs verification_ (state
  what would confirm it). Only confirmed findings set the verdict.
- **Pre-existing:** a defect in code the change neither adds, modifies nor
  newly reaches is not a finding of the change. List it under _Pre-existing_
  below, not here.
- One root cause per finding; mention other affected sites inside it.
- Suggest a regression test when a test could have caught it.

## Merge readiness

Score the reviewed revision from the rubric below. The highest-priority
remaining finding sets the ceiling; take the lowest row that applies, and never
average findings or score by their count.

| Score | Meaning                                                                                          |
| ----- | ------------------------------------------------------------------------------------------------ |
| 0/5   | A P0 finding remains.                                                                            |
| 1/5   | A P1 finding remains.                                                                            |
| 2/5   | A P2 finding remains.                                                                            |
| 3/5   | A P3 finding remains, or a required check failed for the reviewed revision.                      |
| 4/5   | No findings, but required verification is missing, stale or blocked, or a named concern remains. |
| 5/5   | No findings, required verification passed for the reviewed revision, and no concern remains.     |

- Only _confirmed_ findings set the score; a _needs verification_ or
  _pre-existing_ item never lowers it.
- Mark the score **provisional** when required verification is missing, stale
  (run on another revision) or blocked; a provisional score is at most 4/5.
- A failed required check caps the score at 3/5 even with no finding; report
  the failure under _Checks_.
- For local changes the score covers only the inspected snapshot. Rescore after
  fixes instead of carrying a score forward.
- The score is an evidence-based assessment, not a guarantee and not
  authorization to merge.

## When a finding blocks merge

- A finding blocks merge only when it is P0, P1 or P2 **and** falls inside the
  change's documented guarantee: the goal, guarantee or acceptance criteria in
  its spec, or the repository rules when no spec narrows them.
- A finding outside that guarantee is not a defect of the change. Reply in one
  line citing the spec section that excludes it, then resolve the thread. If the
  guarantee itself looks wrong, propose a spec change as a follow-up.
- A P3 finding never blocks merge. While it remains open it still sets the
  score.
- Only the user can waive a P2 finding, explicitly and for that finding; an
  agent or reviewer never does. Record the waiver and reason in the thread. A
  waived finding still sets the score. P0 and P1 findings cannot be waived.
- A pre-existing defect never blocks merge, whatever its priority.
- After the final planned review (at most the third round; see the skill's
  _Re-review_), a new finding reopens work only when it meets this blocking
  bar; otherwise reply, resolve or record a follow-up.

## Pre-existing

One line per pre-existing defect worth a follow-up: priority, location, and
the evidence that the change does not reach it. Omit the section when there
are none.

## Semgrep

One line per new Semgrep finding not already raised above: rule, location,
verdict (real, false positive with reason). Omit the section when there are
none, and say "no new findings" in _Checks_.

## No findings

Say so plainly, then list what was not covered: checks not run, paths not
traced, behaviour that needs a running site to confirm.
