# ADR-004: Use Manual Codex Execution Instead Of Nested Codex Exec

## Status

Superseded by [ADR-005](ADR-005-allow-claude-code-to-invoke-codex-exec.md)

> ADR-005는 Codex CLI가 크래시 없는 버전으로 고정된 뒤, **기본 sandbox 하에서만**
> (bypass/danger 플래그 절대 금지) Claude Code가 `codex exec`를 자동 호출하도록 허용한다.
> 아래의 역할 경계와 elevated/bypass 호출의 영구 금지는 그대로 유효하며, "수동 실행
> 단계가 필수"라는 결정만 뒤집힌다. 본 문서는 이력 보존용이자 자동 호출이 불가능할 때의
> 폴백 모델로 남긴다.

## Context

Dogfooding에서 Claude Code가 자신의 Bash 도구로 `codex exec`를 직접 호출해 전체
파이프라인을 구동하려 시도했다. 이는 sandbox 레벨에서 실패했고
(`FAILURE-001-nested-codex-exec-sandbox-conflict.md`), 크래시와 별개로 구조적 질문을
제기했다 — Claude Code가 Codex를 중첩된 shell 가능 서브프로세스로 띄우는 것이 애초에
타당한가?

## Decision

Claude Code는 elevated sandbox 플래그 유무와 무관하게, Codex CLI를 중첩 구현 에이전트로
직접 호출하지 않는다.

Claude Code의 역할은 Codex 핸드오프 문서(`.codex/task-template.md`) 작성에 한정된다.
사람 운영자가 그 핸드오프를 브리프로 삼아 — 별도 터미널 세션, IDE 통합, 또는 명시적으로
승인된 격리 환경에서 — Codex를 수동으로 실행한다.

`--dangerously-bypass-approvals-and-sandbox`와 `-s danger-full-access`는 어떤 자동화된
Claude Code 워크플로에서도 사용해서는 안 된다. Codex 자체 sandbox가 실패해 elevated
접근 실행만 진행 가능한 상황이면, Claude Code는 권한을 스스로 격상시키지 않고
`docs/harness/human-gate-policy.md`에 따라 멈추고 사람에게 묻는다.

## Alternatives

- 기본 sandbox 실패 시마다 Claude Code가 `danger-full-access`로 `codex exec`를 호출.
  기각: 한 에이전트가 독립 승인 단계 없이 다른 에이전트에 광범위한 shell 접근을
  부여하게 되며, 이는 harness 자율성 모델이 막으려는 바다.
- sandbox 크래시를 고치고 `read-only`/`workspace-write` 하의 자동 `codex exec` 호출 유지.
  향후 가능(Follow-up 참조)하나, 사소한 read-only 명령에서도 크래시가 재현되어 지금은
  실행 불가.
- Claude Code가 per-run 사람 승인 없이 타깃할 수 있는 완전 분리된 사전 승인 일회용
  컨테이너/VM에서 Codex 실행. 현재로선 기각: 여전히 중첩 에이전트 구조이며, 추가
  인프라 없이 개발자 로컬에서 돌도록 의도된 템플릿의 범위를 벗어난다.

## Consequences

Claude Code → Codex → CI → 사람 파이프라인은 핸드오프 생성과 구현 사이에 사람이 운영하는
단계를 유지하므로, dogfooding에서 원래 계획한 것보다 다소 덜 자동화된다. 그 대가로 역할
경계(`ADR-001-separate-claude-code-and-codex-roles.md`)가 온전히 유지된다 — Claude
Code는 계획·리뷰하고, Codex는 자신의 세션과 자신의 승인 설정 하에 구현하며, 어떤
에이전트도 다른 에이전트의 실행 권한을 조용히 획득하지 않는다.

## Follow-up

- 향후 Codex CLI나 OS 업데이트가 sandbox 크래시를 해결하면, `danger-full-access`나 bypass
  플래그가 아닌 기본(비-bypass) sandbox 모드 하에서만 자동 `codex exec` 호출을 재평가.
- 수동 Codex 실행 단계를 `docs/knowledge/template-usage.md`와
  `docs/feedback/dogfooding-plan.md`에 문서화.

## Related Documents

- `docs/failures/FAILURE-001-nested-codex-exec-sandbox-conflict.md`
- `docs/decisions/ADR-001-separate-claude-code-and-codex-roles.md`
- `docs/harness/handoff-policy.md`
- `docs/harness/human-gate-policy.md`
- `docs/harness/autonomy-levels.md`
