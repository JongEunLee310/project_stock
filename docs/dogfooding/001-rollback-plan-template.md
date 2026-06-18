# Dogfooding 001: Add Rollback Plan to Codex Task Packet Template

## Summary

- **Date**: 2026-06-18
- **Issue**: #30
- **PRs**: #31 (main), #32 (fastapi), #33 (spring-boot)
- **Branches tested**: main, fastapi, spring-boot

## Goal

`.codex/CODEX_TASK_PACKET_TEMPLATE.md`에 `## Rollback Plan` 섹션을 추가하는 작업을 통해 Claude Code + Codex 협업 워크플로우 전체를 end-to-end로 검증한다.

## Workflow Exercised

1. Claude Code가 GitHub Issue를 분석한다.
2. Claude Code가 architect-planner 서브에이전트로 영향 범위를 확인한다.
3. Claude Code가 codex-task-writer 서브에이전트로 Codex Task Packet을 작성한다.
4. Claude Code가 implementation-guardian 서브에이전트로 protected file 위반 가능성을 검토한다.
5. Codex가 task packet을 수행하고 변경을 working directory에 남긴다.
6. Claude Code가 결과를 검토하고 커밋/푸시/PR을 생성한다.
7. CI가 자동으로 실행되고 결과를 확인한다.
8. Claude Code가 local-review-policy.md 기준으로 로컬 리뷰를 수행하고 PR 코멘트에 기록한다.
9. 3개 브랜치에 동일하게 적용한다.

## What Worked

- **서브에이전트 파이프라인**: architect-planner → codex-task-writer → implementation-guardian 순서가 자연스럽게 동작했다. 각 에이전트가 역할 범위 내에서 분석/작성/검토를 수행했다.
- **Task packet 품질**: codex-task-writer가 Allowed/Forbidden Scope, Expected Changes, Done Criteria를 구체적으로 작성해 Codex가 범위를 벗어나지 않았다.
- **Codex 결과 품질**: 변경 파일 1개, diff 내용이 task packet 요구사항과 정확히 일치했다. 기존 섹션 구조 불변.
- **CI**: 3개 브랜치 모두 SUCCESS (Template Self-Check, Verify FastAPI Template, Verify Spring Boot Template).
- **3-branch 패턴**: 각 브랜치에서 독립적으로 architect-planner → codex-task-writer → implementation-guardian 파이프라인을 수행해, 브랜치별 차이(검증 명령 등)를 반영한 task packet을 작성할 수 있었다.

## What Did Not Work

### 로컬 리뷰 자동 수행 누락

**현상**: PR을 생성한 후 local-review-policy.md 절차를 수행하지 않고 완료로 처리했다.

**원인**: `docs/harness/local-review-policy.md`가 Claude Code의 메모리에 저장되어 있지 않아서, PR 생성 후 자동으로 로컬 리뷰를 수행해야 한다는 규칙이 다음 세션에 전달되지 않았다. CLAUDE.md에는 "Review PRs locally after PR creation"이 Primary Responsibilities로 명시되어 있고 Required Context에도 포함되어 있으나, 세션 초기에 해당 파일을 읽지 않았다.

**수정**: 사용자 지적 후 즉시 로컬 리뷰를 수행하고 PR 코멘트로 게시했다. 메모리에 "PR 생성 직후 local-review-policy.md 절차 수행 필수" 항목을 저장했다.

**재발 방지**: 메모리 파일 `feedback_local_review_after_pr.md`에 기록. 이후 세션에서 PR 생성 후 자동으로 로컬 리뷰를 수행한다.

### working directory carry-over 주의

**현상**: spring-boot 브랜치에서 Codex가 남긴 uncommitted 변경이 `git checkout dogfooding-001-fastapi` 시점에 fastapi 브랜치로 이동됐다. fastapi에서 먼저 커밋된 후 spring-boot에는 cherry-pick으로 적용됐다.

**원인**: Git은 파일 내용이 동일할 경우 uncommitted 변경을 브랜치 전환 시 함께 이동시킨다.

**수정**: cherry-pick으로 spring-boot에도 동일 변경을 적용, 결과는 동일하나 의도하지 않은 순서였다.

**재발 방지**: Codex가 working directory에 변경을 남긴 경우, 브랜치 전환 전에 반드시 stash 또는 커밋한다.

## Findings

- `.codex/task-template.md`와 `.codex/CODEX_TASK_PACKET_TEMPLATE.md` 사이의 포맷 비대칭이 확인됐다 (task-template.md에는 Rollback Plan 섹션 없음). 향후 별도 이슈로 통일 검토 가능.
- 브랜치별로 Verification 명령이 다르기 때문에 (main: 없음, fastapi: uv run 계열, spring-boot: ./gradlew build), 브랜치별 별도 task packet 작성이 필요하다. 문서 전용 변경이라도 이 차이를 반영해야 Done Criteria가 정확하다.

## CI Results

| PR | Branch | Job | Result |
|----|--------|-----|--------|
| #31 | main | Template Self-Check | SUCCESS |
| #32 | fastapi | Verify FastAPI Template | SUCCESS |
| #33 | spring-boot | Verify Spring Boot Template | SUCCESS |

## Follow-up Actions

- [ ] `.codex/task-template.md`에도 Rollback Plan 섹션 추가 여부 검토 (별도 이슈)
- [x] 메모리에 로컬 리뷰 의무 저장 완료
- [ ] Codex uncommitted 변경 취급 절차 보강 검토
