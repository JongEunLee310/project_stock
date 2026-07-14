# Codex Handoff Task

## Source Issue

이슈 #293 · #294 — research_queue 후속 라운드. 설계:
`docs/designs/293-294-research-queue-followups.md` (먼저 전체를 읽는다).

## Task Summary

PR #292 로컬 리뷰 후속 세 건을 처리한다. #293은 `ResearchStatus`에
`PENDING_ANALYSIS`를 추가하는 additive 계약 변경, #294는 계약 변경이
없는 방어 정리 두 건이다.

## Goal

- `last_updated_at`이 `None`인 자산이 `ANALYZED`로 분류되지 않고
  `PENDING_ANALYSIS`로 분류된다 (완성도 규칙은 그대로 우선).
- `list_queue` 한 요청 안에서 기준 시각(`utc_now()`)이 한 번만
  계산된다.
- 우선순위 목록에 없는 시그널 타입만 있는 자산의 `signal_type`이
  `None`으로 응답된다.

## Implementation Scope

- `app/domains/research_queue/schema.py` — `ResearchStatus`에
  `PENDING_ANALYSIS` 추가.
- `app/domains/research_queue/service.py`
  - `_derive_status` 판정 우선순위에 `last_updated_at is None →
    PENDING_ANALYSIS`를 STALE 판정 앞에 추가 (설계 §2 표).
  - `_NEEDS_RESEARCH_STATUSES`에 `PENDING_ANALYSIS` 포함.
  - `list_queue` 진입 시 기준 시각을 한 번 계산해
    `_build_summary`·`_apply_filter`에 전달.
  - `_top_signal_type`의 `min()` fallback을 `None` 반환으로 교체.
- `docs/designs/266-research-queue-contract.md` — §4.1 판정 표에
  `PENDING_ANALYSIS` 행 반영.
- `docs/api/frontend-api-spec.md` — research-queue 계약의
  `research_status` 값 목록 갱신.
- `tests/test_research_queue.py` — 설계 §5의 시나리오 추가.

## Out of Scope

- 완성도 배점·30/70 임계값·다른 상태의 판정 규칙 변경
- 응답 스키마의 다른 필드 변경
- FE 수정 (별도 repo)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`chore/293-294-research-queue-followups`)에서 그대로
  작업한다. 새 브랜치 생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 설계 문서·이 태스크 문서·구현이 같은 PR에 함께 실린다.
