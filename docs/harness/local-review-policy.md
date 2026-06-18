# Local Review Policy

Claude Code review happens after PR creation.

The review is local by default, not a GitHub Actions job. This template does not configure Claude GitHub Action.

## Review Scope

Claude Code should review:

- PR diff.
- Related issue.
- Codex handoff task.
- CI result.
- Protected file changes.
- Documentation impact.
- ADR need.
- Failure Record need.
- Domain knowledge impact.

## Review Records

Review files are stored permanently at:

`docs/reviews/pr-{number}.md`

Create the file before posting the comment. Reusable findings should also be promoted into ADRs, failure records, or the knowledge base.

## Follow-up After Review Feedback

When Codex addresses review feedback on an existing PR:

- **Do not create a new PR.** Push the fix commits directly to the existing branch.
- Add a follow-up review comment to the **same PR** describing what changed and confirming the fix.
- Use `gh pr comment <PR_NUMBER> --body-file docs/reviews/pr-<PR_NUMBER>.md`.
- Only open a new PR if the branch itself was deleted or the scope changed significantly enough to warrant a new issue.

## Approval

Claude Code must not approve PRs automatically. Human reviewers own final approval.
