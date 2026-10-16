# Review report

One report per review. Keep it short enough to read in a minute; detail goes in
the findings, not in narration. The app's review contract may add fields (a
score, usage, a fix prompt); include them where it says.

## Header

- **Reviewed:** `<base sha>..<head sha>` (PR link or branch), and the installed
  Frappe version used as reference.
- **Verdict:** changes requested when any P0–P2 finding remains; otherwise no
  blocking findings.
- **Checks:** each command you ran with its observed exit status (Semgrep,
  tests, linters), existing CI results cited as CI evidence, and checks not run
  with the reason.

## Findings

Order by severity, then by file. Each finding:

```markdown
### [P1] Investor can read another portfolio's transactions

`app/api/portfolio.py:42-57`, confirmed

`get_transactions` passes `ignore_permissions=True` to `frappe.get_all`, so the
`permission_query_conditions` hook in `hooks.py` never runs for this endpoint.

- **When:** any logged-in user calls the method with another portfolio's name.
- **Evidence:** `frappe/model/db_query.py:674` (v16.51.0) adds match
  conditions only when `ignore_permissions` is false; no other check guards the
  call path from `@frappe.whitelist()` at line 38.
- **Fix:** use `frappe.get_list` and keep the hook; add a test that an investor
  without a User Permission on the portfolio gets `frappe.PermissionError`.
```

The example is illustrative; every path, line and version in a real finding
comes from code you read.

- **Severity**
  - **P0:** broad, immediate harm: data exposure across tenants or users, data
    destroyed or silently corrupted, a critical flow broken for everyone.
  - **P1:** a security, money or data-loss defect below P0.
  - **P2:** a correctness defect or regression that must be fixed before merge,
    including a missing test for new risky behaviour.
  - **P3:** a real but minor defect worth fixing.
- **Location:** the file and line range in the head revision, on lines that are
  in the diff when the finding is about the change, so it maps to a GitHub
  inline comment. Use a file-level or PR-level note only when no line fits.
- **Status:** _confirmed_ (traced or reproduced) or _needs verification_ (state
  what would confirm it). Only confirmed findings set the verdict.
- One root cause per finding; mention other affected sites inside it.
- Suggest a regression test when a test could have caught it.

## Semgrep

One line per new Semgrep finding not already raised above: rule, location,
verdict (real, false positive with reason). Omit the section when there are
none, and say "no new findings" in _Checks_.

## No findings

Say so plainly, then list what was not covered: checks not run, paths not
traced, behaviour that needs a running site to confirm.
