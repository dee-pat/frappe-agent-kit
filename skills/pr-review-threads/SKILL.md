---
name: pr-review-threads
description: Resolve GitHub pull request review conversations whose findings are verified as fixed at the current head. Use during a requested PR review or review-fix workflow, or when asked to reconcile or resolve review threads.
---

# Resolve PR review threads

As part of a requested GitHub PR review or review-fix workflow, resolve existing
review conversations whose findings are verified as addressed by subsequent
changes; include this reconciliation in completion rather than leaving it for a
separate user request.

## Steps

1. **Fetch every unresolved thread at the current head.** Replace `OWNER`,
   `REPO` and `NUMBER`; `--paginate` follows `endCursor` until every page is
   read.

   ```bash
   gh api graphql --paginate -F owner=OWNER -F repo=REPO -F pr=NUMBER -f query='
   query($owner: String!, $repo: String!, $pr: Int!, $endCursor: String) {
     repository(owner: $owner, name: $repo) {
       pullRequest(number: $pr) {
         headRefOid
         reviewThreads(first: 50, after: $endCursor) {
           pageInfo { hasNextPage endCursor }
           nodes {
             id isResolved isOutdated path line
             comments(first: 50) { nodes { author { login } body url createdAt } }
           }
         }
       }
     }
   }'
   ```

2. **Verify each thread on its own.** Read the finding and its replies, then
   check the current code and the relevant change history. An outdated marker or
   a reply claiming a fix is not proof. Check older duplicates of a newer
   finding separately; a fix that was later lost does not qualify.
3. **Decide.** Resolve only findings fully addressed at the current head. Leave
   partial fixes, regressions, unanswered questions and still-applicable
   findings open.
4. **Wait for evidence when you made the fix.** Run the app's applicable
   verification gates and wait for required CI on the pushed revision before
   resolving its conversations. If the head changes during reconciliation,
   recheck the affected findings against it.
5. **Resolve** with the platform's resolve-thread operation, which keeps the
   discussion and other reviewers' comments:

   ```bash
   gh api graphql -F id=THREAD_ID -f query='
   mutation($id: ID!) {
     resolveReviewThread(input: { threadId: $id }) { thread { id isResolved } }
   }'
   ```

   Resolution alone does not authorize posting replies or changing review
   approvals.

6. **Read back** thread states with step 1's query. Report the resolved count
   and remaining open issues, with links when useful. If permissions or tools
   prevent resolution, report the exact blocker and which verified
   conversations remain open.
