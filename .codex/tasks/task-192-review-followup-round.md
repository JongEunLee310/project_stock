# Codex Handoff Task

## Source Issue

이슈 #309 — 리뷰 후속 정리 라운드. 설계:
`docs/designs/309-review-followup-round.md` (먼저 전체를 읽는다 —
항목별 출처·파일·내용 표가 있다).

## Task Summary

PR #283–#291 로컬 리뷰의 비차단 소견 중 미조치 8건을 한 라운드로
정리한다. 7번(수집 카운터 분리)만 태스크 리포트 additive이고 나머지는
와이어 계약 변경이 없다.

## Goal

설계 문서 §1 표의 8개 항목이 모두 반영되고, 기존 테스트가 회귀 없이
통과한다.

## Implementation Scope

설계 §1 표의 8건 그대로. 요약:

1. `app/api/v1/endpoints/assets.py` — earnings-summary description의
   "deterministic mock" 문구 정정.
2. `app/domains/valuation/history.py` — 도달하지 않는
   `if eps is not None` 필터 제거.
3. `app/domains/signals/repository.py` — `prev_captured_at`에만
   `type_coerce`를 쓰는 이유 한 줄 주석.
4. `app/domains/benchmark/service.py` — 동일 (symbol, market)의
   `get_daily_closes` 중복 호출을 캐싱으로 제거 + 조회 1회 검증 테스트.
5. `app/adapters/market/mock.py` — `fcf_yield` 음수 범위 의도 주석.
6. `docs/knowledge/workflow.md` — `uv run pytest` 통과 사실·conftest
   두 단계 프로바이더 격리 한 줄 보강.
7. 리포트 수집 태스크 — 리포트 저장 성공과 이벤트 수집 성공을 별도
   카운터로 분리 (기존 집계 회귀 없음 + 이벤트 실패 별도 카운터 테스트).
8. quote 캐시 설계 문서 — `as_of` 의미(캐시 저장 시각, TTL 60초 내
   과거 가능) 명문화.

## Out of Scope

- 응답 계약(스키마) 변경, 판정 규칙 변경
- #293·#294·#300 등 별도 이슈로 등록된 항목

## Protected Files

없음.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Constraints

- 현재 브랜치(`chore/309-review-followup-round`)에서 그대로 작업한다.
  새 브랜치 생성·checkout 금지.
- 커밋은 한국어 `type: 본문` 형식으로 작성한다.
- 설계 문서·이 태스크 문서·구현이 같은 PR에 함께 실린다.
