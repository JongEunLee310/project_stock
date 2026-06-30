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

The review is written to a durable, versioned file:

`docs/reviews/pr-<number>.md`

This file is committed, not a throwaway under `tmp/`. The PR conversation remains the place to publish the review for discussion, and reusable findings should still be promoted into docs, ADRs, failure records, or the knowledge base.

## Review Format

Every review record uses the same section order and headers:

1. `## Review Summary`
2. `## Blocking`
3. `## Suggestions`
4. `## Questions`
5. `## CI Result`
6. `## Documentation Impact`
7. `## Final Recommendation`

Use the fixed headers even when a section is empty (state "None").

Write the section bodies in Korean. The section headers stay as the fixed labels above; only the prose inside each section is Korean. This matches the global preference (responses in Korean) and keeps BE/FE review records consistent.

Keep the tone polite and plain — use the `~합니다` register and explain what changed and why in natural sentences. Avoid both stiff declarative endings (`~한다`/`~됨`) and overly casual or figurative phrasing (`~어요`, 비유). Preserve technical identifiers and information density; soften the register, not the substance. The same tone applies to PR descriptions, not only review records.

Use sentence structures that read naturally in Korean. Avoid English-calque phrasing, over-compressed noun endings that drop the verb (e.g. "~ 정리.", "~ 일관."), arrow (`→`) clause joining, and piling multiple modifiers onto a single noun so the line is hard to parse in one pass. Unpack such cases into sentences with a clear subject and predicate, keeping identifiers and information density intact — fix the structure, not the substance. 상세 원칙은 `design-record-policy.md` 참조.

## Handling Review Feedback

When the posted review comment contains a **Blocking** finding or any change the review says must be made, Claude Code does **not** stop and wait for the human. It drives the fix loop:

1. **Hand the required changes to Codex.** Claude Code does not edit implementation code itself (per `agent-role-policy.md`); it writes the review findings into a Codex handoff (or `.codex/prompts/`) stating what must change and why, and triggers Codex.
2. **Codex pushes to the same feature branch.** It does **not** open a new PR — the push updates the existing PR. Do not fragment a single review cycle across multiple PRs.
3. **Claude Code re-reviews the updated PR** and posts the follow-up review as a **new comment on the same PR** (`docs/reviews/pr-<number>.md` updated, then `gh pr comment`).
4. **Repeat** from step 1 while the latest review still has a Blocking finding or required change.
5. **Then wait.** Once the review converges to no blocking change, Claude Code stops and waits for the human to approve and merge.

This loop is bounded by the review converging. If the same finding recurs without progress after a few cycles, stop the loop and escalate to the human instead of continuing — do not run an unbounded fix loop.

A review with no Blocking finding and no required change goes straight to the wait step; there is nothing to hand to Codex.

## Comment Wording

When publishing the review comment, the closing line about merge authority must read:

> 최종 머지 권한은 개발자에게 있습니다.

Do not use phrasing that frames it as a robot addressing a person (e.g. "머지는 인간 소유", "머지 권한: 사람"). The intent is unchanged — Claude Code never merges — but the wording stays developer-centric and natural.

## Comment Identity

리뷰 기록·리뷰 스레드 답글·PR 코멘트는 개발자 계정이 아니라 GitHub App 봇
`claude-code-comment-bot[bot]` 명의로 게시한다. 그래야 PR 스레드가 자문자답이 아니라
사람 ↔ AI 대화로 읽힌다. 커밋과 push는 개발자 계정 명의를 유지하며(`Co-Authored-By`
트레일러 포함), 봇 명의로 바꾸는 것은 코멘트·리뷰 레이어뿐이다.

게시는 `gh`를 직접 쓰지 않고 래퍼를 경유한다.

- `scripts/claude-bot-gh.sh <gh 인자>` — 1시간짜리 GitHub App installation token을 발급해
  그 한 번의 `gh` 호출에만 `GH_TOKEN`으로 주입한다. 예:
  `scripts/claude-bot-gh.sh pr comment <number> --body-file docs/reviews/pr-<number>.md`.
- `scripts/claude-bot-token.py` — 토큰 교환기. `uv run --with pyjwt --with cryptography`로
  일회성 실행해 프로젝트 의존성을 오염시키지 않는다.

자격은 repo 밖에 둔다. App ID는 `CLAUDE_BOT_APP_ID` 환경변수(비대화형 zsh는 `.zshrc`가
아니라 `.zshenv`를 읽으므로 거기에 둔다), App private key는
`~/.config/claude-bot/private-key.pem`(chmod 600)에 둔다. App은 Pull requests·Issues
read/write 권한이 필요하고 대상 repo(BE·FE 모두)에 설치되어 있어야 한다.

작성자 확인은 코멘트 목록 정렬이 페이지네이션 탓에 부정확하니 코멘트 id로 직접 조회한다.
`gh api repos/<owner>/<repo>/issues/comments/<id> --jq .user.type`가 `Bot`이면 정상이다.

## Approval

Claude Code must not approve PRs automatically. Human reviewers own final approval.
