# Default Workflow

## 1. Issue Creation

Create an issue with purpose, background, requirements, out-of-scope items, verification expectations, and documentation impact.

For larger work, structure it as a strategy (Epic) issue plus sub-issues, and fill in the issue and milestone metadata, per `docs/harness/issue-authoring-policy.md`.

## 2. Claude Plan

Claude Code reads the issue and relevant docs, then creates a plan.

## 3. Codex Handoff

Claude Code creates a Codex handoff task using `.codex/task-template.md`.

## 4. Codex Implementation

Codex implements only the handoff scope, updates tests, and runs local verification.
`tests/conftest.py`가 환경 변수와 import 후 `settings` 객체를 두 단계로 mock provider에 격리하므로, 별도 env 접두사 없이 `uv run pytest`가 통과한다.

## 5. PR Creation

Create a PR using `.github/pull_request_template.md`.

## 6. CI Feedback

GitHub Actions runs project-specific verification. CI failures are feedback for Codex.

## 7. Review Record

Record local review in `docs/reviews/pr-{number}.md` and post to the PR conversation using `gh pr comment <PR_NUMBER> --body-file docs/reviews/pr-<PR_NUMBER>.md`.

## 8. Claude Local Review

Claude Code reviews the PR locally after PR creation.

## 9. Document Promotion

Promote reusable review findings into docs, ADRs, failure records, or knowledge base entries.

## 10. Human Merge

Humans approve and merge after risk, CI, and review status are acceptable.

## Skill Usage

이 프로젝트는 백엔드 스킬 `fastapi-patterns`·`python-testing`·`api-design`을 활성화해 구현·리뷰의 참조 근거로 사용한다. Claude Code는 `.claude/settings.json`의 `skillOverrides`로 활성화되고, Codex는 `.codex/instructions.md`가 이 스킬들을 참조한다. 스킬은 참조 자료이며 자율 워크플로를 발동시키지 않는다. 상세는 `docs/agent/skill-policy.md`를 따른다.
