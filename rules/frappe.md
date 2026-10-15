## Shared Frappe rules

Frappe v16 rules shared across apps; the app's own rules win on conflict. Use
`frappe-app-dev` for Frappe work, `code-style` when writing code,
`frappe-code-review` when reviewing, and `frappe-migration` for patches,
indexes, DocPerms and schema changes.

- Use v16 APIs and supported hooks; never monkey-patch core.
- User-facing multi-record reads use `frappe.qb.get_query` with
  `ignore_permissions=False`. Use `ignore_permissions=True` only in reports,
  migrations and admin invariant checks whose caller's permission is verified
  separately and documented.
- At every whitelisted boundary, check runtime types with `isinstance` before
  any read, existence or permission check; reject lists and dicts where a string
  is expected.
- Permission-query hooks build SQL only from fixed identifiers and values
  escaped with Frappe's database API.
- No `frappe.db.commit()` or `rollback()` in controllers, hooks, request
  handlers or shared services.
- Normalize dates with `frappe.utils.getdate`; never compare date strings with
  date objects.
- Async form handlers return their Promise and carry a per-form request token so
  a stale response cannot overwrite newer state.
- When a backend field or permission reaches the UI, update the client and one
  browser assertion in the same change; server tests own the full matrix.
- Background jobs and patches are idempotent and safe to rerun.
- For `>`, `>=`, `<`, `<=` rules, test greater, less and equal.
- A gate passes only when run on the current change with an observed zero exit
  status. Report an unavailable gate as a blocker, and never weaken an assertion
  to make CI pass.
