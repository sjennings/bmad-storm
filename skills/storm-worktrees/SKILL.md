---
name: storm-worktrees
description: Isolated parallel Git worktree lanes for concurrent work. Every branch, worktree, merge, rebase, cherry-pick, reset, or remove operation is approval-gated, with mandatory dirty-tree inspection and pre-integration checks.
---

# Storm Worktrees

Parallel lanes need physical isolation when their file ownership cannot be kept disjoint in one checkout. This skill wraps Git worktree operations with explicit authority gates. It exists only where the operator has granted Git authority for the session; the default repository posture (no commit/push without explicit authority) is unchanged.

## Approval gates (non-negotiable)

Every one of these requires explicit operator approval immediately before running:

- `git worktree add` / `remove` / `prune`
- branch creation, deletion, or rename
- merge, rebase, cherry-pick, reset, or any history mutation
- commit and push inside a lane

No batch approvals: each consequential operation is shown with its exact command and blast radius before it runs.

## Lane lifecycle

1. **Create** — after approval, add the worktree on a task-scoped branch. Record the lane (path, branch, owning todo) in the orchestration lane record.
2. **Inspect before touching** — `git status` and `git diff` in the target worktree before any operation. A dirty tree the lane did not create stops the lane: report, never clean up someone else's changes.
3. **Work** — normal Storm rules apply inside the lane (goal/Linear gates, TDD seams, specialist ownership).
4. **Pre-integration checks** — before any approved merge/rebase back: the lane's build and tests run green, the diff is reviewed through the normal review path, and the integration target is clean and at the expected commit.
5. **Remove** — only after integration is confirmed and the operator approves removal; verify no unmerged or untracked work remains (`git status`, `git log` against the integration target) before `worktree remove`.

## Boundaries

- Never force-push, never delete a branch with unmerged work without showing the operator exactly what would be lost, never run destructive Git in a worktree the lane does not own.
- Worktrees isolate files, not authority: tracker state, review gates, and the completion-commit policy still flow through the canonical workflow.
