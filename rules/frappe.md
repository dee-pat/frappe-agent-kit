## Shared Frappe rules

These rules apply to every Frappe v16 app that embeds them. The app's own rules
add to them and win on conflict. Use `frappe-app-dev` for Frappe work (load only
the references the task needs), `code-style` when writing code,
`frappe-code-review` when reviewing, and `frappe-migration` for schema and data
migrations. These rules override more permissive skill examples.

### Framework

- Use v16 APIs and supported hooks. No v15-or-older patterns, no monkey-patching
  core, no direct edits to third-party apps unless a fork is the task.
- Multi-record user-facing reads use `frappe.qb.get_query` with
  `ignore_permissions=False`. `get_value`, `exists`, `set_value` and `get_doc`
  are fine when they are the clearest operation and do not bypass permissions.
- `ignore_permissions=True` only for generated reports, migrations and
  administrative invariant checks, where the caller's permission boundary is
  verified separately and the code documents it.
- Permission-query hooks may return SQL only where Frappe requires that shape:
  fixed DocType and field identifiers, every value escaped with Frappe's
  database API, never a client-controlled identifier.
- Validate runtime types with `isinstance` at every whitelisted boundary before
  existence checks, permission checks, set membership or document access; reject
  lists and dicts where a string is expected. Never build SQL by string
  interpolation. Never `eval`/`exec` client input or run a client-supplied
  method path.
- No `frappe.db.commit()`/`rollback()` in controllers, hooks, request handlers
  or shared services, and no autocommit to make bootstrapping look successful.
  One logical change shares the framework-managed request transaction. Avoid
  direct SQL writes; a migration that needs one documents why it is safe and
  handles affected caches and derived data.
- Background jobs are idempotent and safe to retry.
- Normalize dates with `frappe.utils.getdate` and timestamps with Frappe's
  timezone-aware utilities. Never compare date strings with `date`/`datetime`
  objects or use naive `datetime.now()` for timezone-sensitive behaviour.
- Business calculations live in Python. Whitelist a method only when a client
  needs it, and remove the whitelist when it stops being used. Recompute or
  validate client-populated values on the server.
- Async form handlers return their Promise, pass intentional empty values rather
  than omitted `undefined`, and carry a per-form request/version token so a
  stale response cannot overwrite newer form state. Report durable success only
  after the server confirms it.
- Read uploads through the File API and guard against path traversal. Secrets go
  in Password fields and never into logs, exceptions or plain text. Think hard
  before allowing guest access.
- When a backend field or permission reaches Desk, a report or another UI,
  update the client, API payloads, fixtures and one representative browser
  assertion in the same change; server tests own the full permission and
  validation matrix.
- For a stateful or multi-request API, document request/response shapes,
  validation, permissions, atomicity and failure states first. Validate the
  whole operation before mutating, return the canonical server representation,
  protect against stale writes, and require an idempotency key where a duplicate
  request could create data.

### Migrations and invariants

- Data transformations get an idempotent patch registered in `patches.txt`,
  tested by running the registered sequence against representative legacy data,
  including a safe rerun. Schema changes that normal migrate handles get no
  patch.
- Frappe marks registered patches complete before `after_install` runs, so any
  DocPerm, index or other invariant a fresh install needs is also bootstrapped
  idempotently from `after_install` and `after_migrate`. Verify both paths.
- Concurrency-sensitive uniqueness gets a controller check for a useful error
  and a database unique index as the guarantee, installed idempotently.
- Permission patches touch only the `DocPerm` rows they own; never save a parent
  `DocType` just to change permissions.
- Index frequently filtered or joined columns, as code, not ad hoc.

### Change control

- Before deleting or renaming, search imports, hooks, client calls, reports,
  fixtures, patches and tests. Keep public APIs, stored documents, fields,
  reports, hooks, fixtures and patches backward compatible unless a break is
  approved.
- Explain any new dependency and constrain it in the project's files.
- Multi-phase features or migrations start with a short spec and progress note
  (goal, non-goals, design and contract, permissions, failure and recovery,
  tests, rollout, acceptance, follow-ups), proportional to the change and kept
  current. Build a tracer-bullet slice across the layers first.
- Commit, push or open a pull request only when authorized. Confirm the remote
  and base branch first.

### Tests

- Changed behaviour gets a regression test that fails without the change and
  exercises the real code, not a mock of it.
- Tests are deterministic, independent and rerunnable; outcomes never depend on
  generated name suffixes or wall-clock timing. For `>`, `>=`, `<`, `<=` rules,
  test greater, less and equal, and state the equality behaviour.
- Python tests own business rules, permissions, calculations, migrations and API
  validation. Browser tests own visible wiring, with one focused smoke flow per
  critical surface; delayed, failed, stale or retried responses are tested at
  the lowest layer that can, in the browser only for a demonstrated regression.
- Run the targeted test, the affected module and the full app suite.

### Verification

- A gate passes only when you ran it for the current change and saw exit status
  zero. Edits to code, tests, fixtures, metadata, dependencies, scripts or CI
  make earlier results stale.
- Run the app's applicable gates before committing or pushing, and wait for
  required CI before reporting completion.
- A failing or unavailable gate blocks completion: report the exact command and
  what is left unverified. When CI fails, reproduce the traceback in isolation
  and under full-suite ordering; never weaken an assertion to pass.
