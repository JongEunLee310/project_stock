# Task 149 — Escalation 엔진 블라인드 리뷰 적발 반영

## Context

라운드4 이중 블라인드 리뷰(J1 Fable 5 / J2 codex xhigh, `docs/experiments/orchestrator-comparison-round4.md`)가
`experiment/139-escalation-opus` 산출물(8d52ab4)에서 적발한 사항을 반영한다. 설계는
`docs/designs/081-llm-risk-escalation-engine.md`, 결정 기준은 ADR-010.

**브랜치 규칙: 현재 브랜치(`experiment/139-escalation-opus`)에서 그대로 작업한다.
새 브랜치를 만들거나 checkout하지 않는다.** escalation 골격(`app/adapters/llm/escalation.py`
등)은 이 브랜치에 이미 존재한다 — 재구현이 아니라 아래 수정만 수행한다.

## Implementation Scope

1. **설계 문서-구현 모순 해소 (Major).** 현행 라우팅(`LLM_TASK_ROUTES` 전부 cloud)과
   factory 부착 조건에서는 pre-call·post-call 트리거가 발화하지 않는 휴면 상태다.
   - `docs/designs/081-llm-risk-escalation-engine.md`의 "post-call cloud 검증은 현재
     cloud 라우팅에서도 즉시 작동" 서술을 구현과 일치하게 정정(로컬 라우팅 도입 시
     활성화되는 선행 골격임을 명시).
   - `.env.example`·`docs/backend-v0.2.md`의 `LLM_ESCALATION_*` 항목에 현행 구성에서는
     효과가 없고 로컬 라우팅 도입 시 활성화된다는 한 줄 주석 추가.
2. **pre-call 승격의 CloudSafe 표현 가능성 확인 (Major, ADR-010 guardrail).**
   pre-call 승격 경로가 payload sensitivity를 확인해, CloudSafe로 표현 불가능한
   payload는 승격을 건너뛰고 로컬 경로를 유지하도록 한다(하드 실패 금지 — guardrail
   의도는 "승격 생략"). 기존 privacy 판정 수단을 재사용하고 새 추상화를 만들지 않는다.
3. **`escalated` 플래그 의미 일관화 (Minor).** `_verify_with_cloud`에서
   `call_budget.consume()` 예외 등으로 cloud 재호출이 실제 발생하지 않은 경우
   `escalated=False`를 유지한다(현행 cloud client 부재 처리와 동일 의미론).
4. **`_verify_with_cloud` 예외 경로 테스트 보강 (Minor).** budget 초과, boundary 위반
   각각에 대해 원본 결과 반환·`escalated` 값이 의미론과 일치함을 검증하는 테스트 추가.
5. **ADR-010 잔존 문구 정리 (Minor).** Alternatives 절의 보류 시절 문구("지금 평가하지
   않고 …")를 Accepted 상태와 일치하게 정리.
6. **import 정렬 (Minor).** `app/adapters/llm/__init__.py`, `tests/test_briefings.py`,
   `tests/test_watchlist_observations.py`에서 `escalation` import를 알파벳 순서 위치로 이동.

## Out of Scope

- 트리거 신호의 호출부 배선(리스크 급등·손실률·뉴스 감성·이벤트·매수매도 질문의
  실제 산출·전달) — 후속 이슈로 분리 예정.
- 라우팅 정책 변경, `LLM_TASK_ROUTES` 수정.
- escalation 사유(trigger 종류)의 세분화된 관측 필드 추가.

## Protected Files

`app/adapters/llm/router.py`, `app/adapters/llm/privacy.py`, `app/adapters/llm/budget.py`,
`app/adapters/llm/cache.py`, `app/prompts/`, `app/domains/`, `app/scheduler/`,
`alembic/versions/`. 예외: 본 태스크 범위의 문서(`docs/designs/081-*.md`,
`docs/decisions/ADR-010-*.md`, `docs/backend-v0.2.md`, `.env.example`)는 수정 허용.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`

## Notes

- 커밋하지 않는다(오케스트레이터가 검증 후 커밋).
- sync 코드베이스 — `AsyncMock` 금지, 기존 테스트 스텁 패턴 재사용.
