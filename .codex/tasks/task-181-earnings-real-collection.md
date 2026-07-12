# Codex Handoff Task

## Source

이슈 #280 — 실적 실수집. 설계:
`docs/designs/280-earnings-real-collection.md` (먼저 전체를 읽는다).

## Task Summary

`earnings-summary`를 mock 템플릿에서 분기 재무 실수집 기반으로
전환한다. **API 계약(`app/domains/earnings/schema.py`)은 변경하지
않는다.** 구성은 #279(PR #284, 밸류에이션 스냅샷)와 같은 패턴이며,
설계 문서 1~6절을 그대로 따른다:

1. `EarningsReport` 모델(`earnings_reports`, UniqueConstraint
   `(symbol, market, period)`) + alembic 마이그레이션 (단일 헤드).
2. `EarningsProvider` 추상화 + yfinance 구현
   (`quarterly_income_stmt`·`earnings_dates` 매핑 — DataFrame 접근은
   순수 함수 분리, 네트워크 호출 테스트 금지) + 결정적 mock(8분기,
   surprise 양·음 혼재, estimate null 1개) + factory 분기.
3. `EarningsIngestionService` + repository (upsert · get_recent ·
   coverage 집계). 유니버스는 `resolve_assets()` 재사용.
4. `collect_earnings_job`(job_type `earnings_collection`) +
   `/jobs/earnings` enqueue 라우트.
5. `EarningsService.get_summary` 전환 — 최근 8분기 조회 후 최신 4분기
   오름차순, YoY(전년 동기 매칭)·마진·surprise는 조회 시 파생,
   revenue·operating_income·eps 중 하나라도 null인 분기는 응답 제외,
   guidance null·segments 빈 배열, 데이터 부재 시 빈 quarters.
6. research_coverage EARNINGS 축을 `earnings_reports` 집계로 전환.

## Test

설계 문서 Test 절을 그대로 따른다. `tests/test_earnings.py` 재작성,
`tests/test_earnings_ingestion.py` 신규,
`tests/test_research_coverage.py`·`tests/test_api_contract.py` 갱신.
수치 단언은 픽스처 출처 주석, id 리터럴 단언 금지.

## Out of Scope

- #281·#282 범위, schema.py, 가격·뉴스·밸류에이션 수집 로직, 다른
  도메인.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)
  불변.

## Rules

- 현재 브랜치 `feat/280-earnings-real-collection`에서 그대로 작업한다.
  새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
- `uv run alembic heads` (단일 헤드)
