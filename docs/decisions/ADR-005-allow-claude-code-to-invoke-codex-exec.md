# ADR-005: Allow Claude Code To Invoke Codex Exec Under Default Sandbox

## Status

Accepted (supersedes ADR-004)

## Context

ADR-004는 두 가지 이유로 Claude Code의 핸드오프와 Codex 구현 사이에 사람이 운영하는
단계를 유지했다. 초기 `codex exec` 시도가 sandbox 레벨에서 크래시했고(`FAILURE-001`),
한 에이전트가 다른 에이전트에 shell 접근을 부여하는 것이 자율성 모델에 구조적 우려를
제기했다.

두 가지가 바뀌었다:

- **토큰 경제성.** 설계와 구현을 모두 Claude Code로 돌리면 사용량 한도가 빠르게
  소진된다. 구현을 Codex(자체 예산을 가진 별도 도구)로 옮기고 Claude Code가 이를 자동
  트리거하게 하면, 설계/리뷰 루프는 Claude Code에 두면서 구현은 Codex에서 돌아간다 —
  매 작업마다 수동 핸드오프 단계 없이.
- **크래시는 회피 가능.** SIGTRAP 회귀는 중첩 호출 모델 자체가 아니라 특정 Codex CLI
  버전에 국한됐다. Codex CLI를 알려진 정상 버전(0.140.0)으로 고정하면 우회된다.

`ADR-001`의 역할 경계(Claude Code 계획/리뷰, Codex 구현)가 요구하는 것은 *수동* 단계가
아니라 *독립적* 실행 단계다. Codex는 여전히 자신의 세션·모델·sandbox 하에서 돈다.

## Decision

Claude Code는 다음을 **모두** 충족하는 조건에서 구현 단계로 `codex exec`를 자동 호출할
수 있다:

1. **기본 sandbox만** — `read-only` 또는 `workspace-write`.
2. **권한 격상 절대 금지.** `--dangerously-bypass-approvals-and-sandbox`와
   `-s danger-full-access`는 어떤 자동화 워크플로에서도 영구 금지. 기본 sandbox가 작업을
   실행할 수 없으면 Claude Code는 멈추고 사람에게 묻는다(`human-gate-policy.md`) — 결코
   격상하지 않는다.
3. **고정된 CLI.** Codex CLI는 크래시 없는 버전으로 고정(이 머신에서 0.140.0 검증;
   `.codex/CODEX_SETUP_NOTES.md` 참조).
4. **제한된 위임.** `max_depth = 1`(`.codex/config.toml`)로 Codex 서브에이전트가 추가
   서브에이전트를 띄울 수 없게 하고, 서브에이전트는 부모 세션의 sandbox/승인을 절대
   넓히지 않는다.
5. **핸드오프 브리프 여전히 필수.** 작업 패킷(`.codex/task-template.md`)은 여전히
   생성되어 프롬프트로 Codex에 전달된다 — 자동화가 작성된 scope / out-of-scope / 검증
   계약을 없애지 않는다.
6. **휴먼 게이트 불변.** `human-gate-policy.md`의 모든 Mandatory Gate Condition(인증/인가,
   DB 스키마, 인프라/배포, 의존성 변경, CI 설정, 보호 파일, ADR 대상 결정, High/Critical
   위험, 보안 관련 변경)은 자동 구현 단계 실행 **전에** 여전히 사람 승인을 요구한다.

## Consequences

- Level 2(Semi-Autonomous)는 Low/Medium 위험 작업에 더 이상 수동 사람 실행 단계가
  필요 없다. Claude Code가 Codex를 트리거하고 로컬 리뷰로 재개한다. PR 승인과 머지는
  여전히 사람이 소유한다.
- 독립성 보장이 "사람이 Codex를 실행"에서 "Codex가 Claude Code가 격상할 수 없는 자체
  sandbox 세션에서 실행"으로 이동한다. bypass 플래그 금지(2번)가 이를 보존한다.
- 고정 CLI가 불가용하거나 작업이 진짜로 elevated 접근을 필요로 하면, 권한을 격상하는
  대신 수동 실행(ADR-004 모델)으로 폴백한다.

## Alternatives

- **ADR-004 유지(수동 실행).** 기각: 토큰 경제성을 해결하지 못하고, 모든 Low/Medium
  작업에 사람 단계를 더한다.
- **기본 sandbox 실패 시 elevated/bypass 호출 허용.** 기각(ADR-004에서 불변): 독립 승인
  경계를 제거한다.
- **Codex 대신 Claude Code 내부 서브에이전트로 구현.** 토큰 목표상 기각: 내부
  서브에이전트는 이 변경을 촉발한 동일한 Claude Code 예산을 소비한다.

## Follow-up

- 자동 호출에 의존하기 전 Codex CLI를 0.140.0으로 고정하고 `workspace-write` 드라이런을
  검증(`.codex/CODEX_SETUP_NOTES.md`).
- 수정된 Codex 릴리스가 나오면 고정 버전을 재평가.

## Related Documents

- `docs/decisions/ADR-001-separate-claude-code-and-codex-roles.md`
- `docs/decisions/ADR-004-use-manual-codex-execution-instead-of-nested-codex-exec.md` (superseded)
- `docs/harness/handoff-policy.md`, `docs/harness/autonomy-levels.md`, `docs/harness/human-gate-policy.md`
- `.codex/CODEX_SETUP_NOTES.md`, `.codex/config.toml`
- `docs/failures/FAILURE-001-nested-codex-exec-sandbox-conflict.md`
