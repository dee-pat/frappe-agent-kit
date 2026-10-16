## Shared Frappe rules

Frappe v16 rules shared across apps; the app's own rules win on conflict. Use
`frappe-app-dev` for Frappe work, `code-style` when writing code,
`frappe-migration` for patches, indexes, DocPerms and schema changes,
`frappe-code-review` as the review checklist, and `frappe-pr-review` to review a
PR, branch or diff, including your own before opening a PR. Review is read-only
unless the user asks for fixes.

- The installed framework at `<bench>/apps/frappe` is the authority on Frappe
  behaviour: when correctness depends on a lifecycle, permission, transaction or
  hook detail, search it and read the relevant function rather than relying on
  memory or upstream `develop`.
- Use v16 APIs and supported hooks; never monkey-patch core.
- User-facing multi-record reads use `frappe.qb.get_query` with
  `ignore_permissions=False`. Use `ignore_permissions=True` only in reports,
  migrations, admin invariant checks whose caller's permission is verified
  separately and documented, permission-boundary internals that establish the
  boundary rather than sit behind it (for example, reads of role or
  user-permission rows the caller cannot see), and deterministic test or seed
  setup. Each use names the check or boundary it relies on in a comment, and an
  externally invocable helper still needs an administrative boundary.
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
