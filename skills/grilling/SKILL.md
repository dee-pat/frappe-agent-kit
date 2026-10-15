---
name: grilling
description: Grill the user one decision at a time before implementation. Use when asked to grill or stress-test a plan, or when a business-rule, permission, migration, or architecture change still has unresolved high-impact decisions.
---

Interview me about every unresolved decision until we reach a shared understanding. Walk down each branch of the decision tree, resolving dependencies one at a time. For each question, provide a recommended answer.

Ask exactly one question at a time and wait for the answer. If a fact can be found in the repository or through available read-only tools, look it up instead of asking. Decisions remain with the user.

Trigger automatically only for ambiguous, high-impact, hard-to-reverse, or cross-cutting work, especially changes involving:

- monetary calculations, rounding, business dates, or other domain rules the app documents;
- permissions, server-authoritative state, attachments, private data, or security boundaries;
- migrations, schema changes, manual indexes, transaction boundaries, public APIs, or hooks;
- multiple viable architecture, rollout, or user-visible workflow designs.

Do not trigger for a routine implementation whose acceptance criteria are already clear, a single warning or test failure with an evident fix, formatting or lint cleanup, fixture-only changes, or a mechanical refactor. An explicit user request to implement a settled plan also takes precedence over an unnecessary grilling session.

Keep the grilling session read-only. Do not edit files, migrate sites, mutate external systems, commit, or start implementation until the user confirms that shared understanding has been reached. The app's safety rules remain binding throughout.
