# Codex Handoff Task

## Source Issue

이슈 #251 · #259 — 리뷰 후속 라운드. 설계:
`docs/designs/251-259-review-followups.md` (먼저 전체를 읽는다).

## Task Summary

리뷰 후속 이슈 2건을 정리한다. 와이어 계약 변경 없음. 설계 문서
1~2절을 그대로 따른다:

1. `app/domains/analysis/service.py` — `_process_asset`의
   `new_results` 리스트 컴프리헨션을 명시적 루프로 풀어
   `save_with_symbol` 부수 효과와 필터링을 분리한다. 동작 변경 없음,
   기존 테스트 무수정 통과.
2. `app/domains/signals/` — `list_recent_changes`의 전량 메모리 적재를
   제거한다. LAG window 기반 `list_change_rows(since, limit)`를
   repository에 추가해 인접쌍 파생·UNCHANGED 제외·since 필터·정렬·
   limit을 쿼리로 내리고, service는 그 결과로 방향을 분류한다
   (`signal_priority_rank` 재사용, SQL로 우선순위 복제 금지).
   `list_all_ordered`는 제거한다.

## Goal

- `/signals/changes` 응답이 기존과 의미 동일하되, 스냅샷 전량을
  메모리에 적재하지 않는다.
- `_process_asset`의 신규 뉴스 필터링 의도가 명시적 루프로 드러난다.

## Background

- #251은 PR #249 로컬 리뷰 S1, #259는 PR #258 로컬 리뷰 S1의 후속이다.
- UNCHANGED 제외의 NULL 안전 비교는 SQLAlchemy `is_distinct_from`를
  사용한다 (PostgreSQL·SQLite 양쪽 방언 지원 — 설계 2절 확인).
- since 필터는 바깥 행에만 적용하고 인접쌍 파생은 전체 이력 위에서
  계산한다 (현행 의미 유지).

## Implementation Scope

- `app/domains/analysis/service.py`
- `app/domains/signals/repository.py`
- `app/domains/signals/service.py`
- `tests/test_signal_snapshots.py` (테스트 추가)

## Out of Scope

- `app/api/v1/endpoints/signals.py`의 계약(경로·파라미터·응답 모델)
- `build_change`의 외부 의미, `changes_by_asset`·`summary` 경로
- 뉴스 수집 경로·증분 규칙, 스냅샷 캡처 로직
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일) 불변

## Protected Files

없음.

## Requirements

- 설계 문서 2절의 인접쌍·UNCHANGED 제외·since·정렬·limit 규칙을
  정확히 따른다.
- 방향 분류(NEW/CLEARED/ESCALATED/DEESCALATED/CHANGED)·score_delta·
  previous_* 파생은 기존 `build_change` 의미와 완전히 동일해야 한다.
  중복을 줄이려면 방향 분류를 공용 헬퍼로 추출해 재사용해도 된다.
- 신규 SQL은 테스트(SQLite)와 운영(PostgreSQL) 양쪽에서 동작해야 한다.

## Test Requirements

- 기존 `tests/test_signal_snapshots.py` 무회귀.
- 추가: 자산 경계(파티션 정확성), since 경계(이전 스냅샷이 since
  이전), UNCHANGED 제외(동일 타입 연속·모두 NULL·첫 스냅샷 NULL),
  정렬·limit 절단.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

없음 — 와이어 계약 불변이므로 `frontend-api-spec.md` 갱신 불필요.

## ADR Need

불필요 — 신규 도메인·테이블·외부 의존성·아키텍처 결정 없음.

## Failure Record Need

불필요 — 장애 대응이 아닌 계획된 후속 개선.

## Risk Level

Low — 계약 불변 리팩터링이며 기존 테스트와 추가 테스트로 의미 동일성을
증명한다.

## Expected Output

- 위 Implementation Scope 파일들의 수정과 테스트 추가.
- 커밋 1개 (push 금지).

## Rules

- 현재 브랜치 `chore/251-259-review-followups`에서 그대로 작업한다.
  새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- Stay within scope. Do not weaken verification.
- Report assumptions and verification results.
