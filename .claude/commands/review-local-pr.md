# Claude Command: Review Local PR

Review a PR locally after PR creation.

## Required Review Inputs

- PR diff.
- Related issue.
- Codex handoff task.
- CI result.
- Protected file changes.
- Documentation impact.
- ADR need.
- Failure Record need.
- Domain knowledge impact.

## Output Format

Write or recommend writing the result to:

`tmp/claude-pr-review.md`

Use this structure:

## Review Summary

## Blocking Issues

## Suggestions

## Questions

## CI Result

## Documentation Impact

## Final Recommendation

## Publishing Commands

Suggested commands:

```bash
gh pr comment <PR_NUMBER> --body-file tmp/claude-pr-review.md
gh pr review <PR_NUMBER> --comment --body-file tmp/claude-pr-review.md
gh pr review <PR_NUMBER> --request-changes --body-file tmp/claude-pr-review.md
```

Do not approve PRs automatically.
