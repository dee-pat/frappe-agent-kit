---
name: frappe-migration
description: Schema and data migrations for Frappe apps. Use when renaming, removing, or retyping a DocType or field, writing or retiring a patch in `patches.txt`, adding a manual index or DocPerm invariant, or deleting a deprecated code path.
---

# Frappe Migration

Change shape in _expand/contract_ phases so every deployed site migrates safely, then retire what is left behind.

## Sources of truth

The app's own guidance wins where it is more specific. Before changing anything, find:

- its `AGENTS.md` rules for patches, manual indexes, DocPerms and `after_install`;
- its lifecycle harness: a regression that runs the registered patch sequence on a temporary site with representative legacy data, then drops the site. If the app has none, say so and propose one before a rename, retype or staged constraint;
- its verification guide for gates and evidence, and any data-model doc that must change with a DocType, `Link` or `Table` change;
- any app migration skill or notes listing app-specific references to update.

## Pick the branch

Read only the reference the branch names.

- **Additive** (new DocType, field, index, DocPerm): normal Frappe migrate handles schema; add a patch only for data or an invariant, and bootstrap invariants in `after_install` too. Model sync drops manual indexes that DocField metadata cannot declare, and re-importing a changed DocType JSON replaces its DocPerm rows with the JSON's, so also reapply manual indexes and patch-managed DocPerms idempotently from `after_migrate`; a logged patch never runs again. Three schema exceptions need staging: a new field with a default on an existing Single, a new `unique` field, and a new `reqd` field on a populated DocType. Read [staged-constraints.md](references/staged-constraints.md).
- **Tighten an existing field** (non-unique to unique, optional to required): stage it across releases. Read [staged-constraints.md](references/staged-constraints.md).
- **Rename** (DocType or field): one release, one patch, only when the deployment stops every previous-release worker before migrate and a rollback restores the pre-migrate backup. Read [renames.md](references/renames.md). Otherwise old and new code write different columns or query a renamed table, so treat the rename as a retype.
- **Remove or retype** (field, DocType, `Link` target, `Table` ownership): expand/contract across releases. Read [expand-contract.md](references/expand-contract.md).
- **Retire** (one-time patch, deprecated path, dead code): see _Retirement_ below.

## Retirement

A one-time data patch is retirable only after the user confirms every deployed site has run it and that no backup, staging copy, or offline site still supported for restore and upgrade predates it; such a site would upgrade without the transformation. If those restore paths stay supported, keep the patch registered. A fresh install marks it complete without running it. In one change: remove its `patches.txt` line and module, any `after_install`/`after_migrate` entry, its tests, its lifecycle fixtures and assertions, and its references in the app's migration docs. Invariant patches (DocPerms, manual indexes) stay, because fresh installs and migrates both need them.

For deprecated code paths, find every consumer first (`git grep`, `hooks.py`, whitelisted method names called from Desk JS and any SPA, report JSON) and remove the path only when the count is zero. Done when nothing imports, routes to, or calls the removed name.

## Verify

A fresh install of the current tree creates only the new schema and marks every patch complete, so a lifecycle fixture must reconstruct the schema state of the release before the migration under test. Read [lifecycle-fixtures.md](references/lifecycle-fixtures.md) before writing or changing one.

Run the lifecycle sequence for any patch change, plus the app's applicable gates, and drop the temporary site afterwards whether it passed or failed.
