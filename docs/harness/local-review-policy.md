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

## Review Format

모든 리뷰 파일과 PR 코멘트는 아래 섹션 순서와 헤더를 따른다.

```markdown
## Review Summary

PR #{number} — {이슈 목록} 구현

{전체 판정 1~2문장. 충족 여부, 패턴 일관성, 주요 발견 건수 요약.}

---

## Blocking Issues

없음. (또는 블로킹 이슈 상세)

---

## Suggestions

### 1. {제목} ({Minor/Major})

**위치:** {파일:라인}

{설명}

**권장 수정 방향:** {수정 방향}

---

## Questions

없음. (또는 질문 상세)

---

## CI Result

CI 대기 중 / 통과 / 실패. 로컬 검증 결과:

- `uv run ruff check .` — {결과}
- `uv run mypy .` — {결과}
- `uv run pytest {파일} -v` — {결과}

---

## Documentation Impact

{영향 없음 또는 상세}

ADR 불필요/필요. Failure Record 불필요/필요.

---

## Final Recommendation

**{판정}** — {근거 1문장}
```

## Follow-up After Review Feedback

When Codex addresses review feedback on an existing PR:

- **Do not create a new PR.** Push the fix commits directly to the existing branch.
- Add a follow-up review comment to the **same PR** describing what changed and confirming the fix.
- Use `gh pr comment <PR_NUMBER> --body-file docs/reviews/pr-<PR_NUMBER>.md`.
- Only open a new PR if the branch itself was deleted or the scope changed significantly enough to warrant a new issue.

## Approval

Claude Code must not approve PRs automatically. Human reviewers own final approval.
