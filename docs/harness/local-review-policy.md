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

When the posted review comment contains a **Blocking** finding or any change the review says must be made, Claude Code does **not** stop and wait for the human. It drives the fix loop:

1. **Hand the required changes to Codex.** Claude Code does not edit implementation code itself (per `agent-role-policy.md`); it writes the review findings into a Codex handoff (or `.codex/prompts/`) stating what must change and why, and triggers Codex.
2. **Codex pushes to the same feature branch.** It does **not** open a new PR — the push updates the existing PR. Do not fragment a single review cycle across multiple PRs.
3. **Claude Code re-reviews the updated PR** and posts the follow-up review as a **new comment on the same PR**: update `docs/reviews/pr-<number>.md`, then `gh pr comment <PR_NUMBER> --body-file docs/reviews/pr-<PR_NUMBER>.md`.
4. **Repeat** from step 1 while the latest review still has a Blocking finding or required change.
5. **Then wait.** Once the review converges to no blocking change, Claude Code stops and waits for the human to approve and merge.

This loop is bounded by the review converging. If the same finding recurs without progress after a few cycles, stop the loop and escalate to the human instead of continuing — do not run an unbounded fix loop. Only open a new PR if the branch itself was deleted or the scope changed significantly enough to warrant a new issue.

A review with no Blocking finding and no required change goes straight to the wait step; there is nothing to hand to Codex.

## Approval

Claude Code must not approve PRs automatically. Human reviewers own final approval.
