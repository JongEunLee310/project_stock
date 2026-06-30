# ADR-001: Separate Claude Code And Codex Roles

## Status

Accepted

## Context

한 에이전트가 경계 없이 계획·구현·리뷰·결정 기록을 모두 수행하면 AI 보조 개발은
리뷰하기 어려워진다.

## Decision

책임을 분리한다:

- Claude Code = 오케스트레이터 겸 리뷰어.
- Codex = 구현자.
- CI = 피드백 센서.
- 사람 = 최종 소유자.

## Alternatives

- 계획·구현·리뷰를 한 에이전트가 모두 수행.
- GitHub Actions에서 Claude Code 리뷰를 자동 실행.
- CI가 모든 리뷰 피드백을 소유.

## Consequences

역할 분리는 범위·리뷰·책임 소재를 더 명확하게 한다. 핸드오프 오버헤드가 늘지만, 그
오버헤드가 더 나은 리뷰 기록과 더 안전한 사람 승인을 만든다.

## Follow-up

프로젝트별 템플릿은 검증 명령과 보호 파일을 커스터마이즈해야 한다.

## Related Documents

- `docs/harness/agent-role-policy.md`
- `docs/harness/handoff-policy.md`
- `docs/harness/local-review-policy.md`
