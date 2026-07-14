# Codex Handoff Task

## Source Issue

이슈 #300 — research-summary `counter_view` 필드 제거. 이슈 본문을
먼저 읽는다. 선행 조건(FE counter_points 전환, FE PR #209 머지)은
충족되었다.

## Task Summary

#298(PR #299)에서 additive로 추가한 `counter_points`로 FE 전환이
완료되었으므로, 호환용으로 유지하던 구계약 `counter_view` 필드를
계약·mock 템플릿·테스트·스펙 문서에서 제거한다.

## Goal

- research-summary 응답에 `counter_view`가 더 이상 존재하지 않는다.
- `counter_points`와 다른 응답 필드는 값·순서 회귀가 없다.

## Implementation Scope

- `app/domains/research_summary/schema.py` — `counter_view` 필드 제거.
- `app/domains/research_summary/service.py` — mock 템플릿의
  `counter_view` 데이터 제거.
- `tests/test_assets.py`·`tests/test_api_contract.py` —
  `counter_view` 단언 제거, "필드가 존재하지 않는다" 단언으로 교체.
- `docs/api/frontend-api-spec.md` — research-summary 계약에서
  `counter_view` 제거.
- `docs/designs/298-counter-points.md` — 제거 완료 사실을 한 줄
  후기(변경 이력)로 남긴다 (기존 본문 재작성 금지).

## Out of Scope

- `counter_points` 구조·내용 변경
- FE 수정 (이미 완료)

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`chore/300-remove-counter-view`)에서 그대로 작업한다.
  새 브랜치 생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 이 태스크 문서와 구현이 같은 PR에 함께 실린다.
