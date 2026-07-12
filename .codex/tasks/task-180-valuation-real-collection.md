# Codex Handoff Task

## Source

이슈 #279 — 밸류에이션 현재 지표 실수집. 설계:
`docs/designs/279-valuation-real-collection.md` (먼저 전체를 읽는다).

## Task Summary

`valuation-metrics`의 `value`를 mock 템플릿에서 스냅샷 실수집 기반으로
전환한다. **API 계약(`app/domains/valuation/schema.py`)은 변경하지
않는다.** 구성 요소는 설계 문서의 1~6절을 그대로 따른다:

1. `ValuationSnapshot` 모델 + alembic 마이그레이션 (단일 헤드 유지,
   UniqueConstraint `(symbol, market, as_of)`).
2. `ValuationProvider` 추상화 + yfinance·mock 구현 + factory 분기.
   yfinance의 `Ticker.info` 매핑과 fcf_yield 산출은 설계 문서 표를
   따르고, info 접근·값 변환은 순수 함수로 분리해 그 부분만 테스트한다
   (네트워크 호출 테스트 금지).
3. `ValuationIngestionService` + repository (upsert ·
   get_latest · coverage용 집계). 수집 유니버스는
   `PriceUniverseResolver.resolve_assets()`(신규 분리 — 워치리스트·
   포트폴리오 합집합, 벤치마크 제외)를 쓰고 기존 `resolve()` 동작은
   회귀 없이 유지한다.
4. `collect_valuation_job` worker job (job_type
   `valuation_collection`) + `/jobs/valuation` enqueue 라우트.
5. `ValuationService.get_metrics` 전환 — 최신 스냅샷 기반 value,
   median·percentile null 유지, 스냅샷 부재 시 전부 null. profile
   판정: FINANCIAL(sector `Financial Services`) > DEFICIT(per·
   forward_per 모두 null) > GENERAL. highlighted_metrics는 기존
   profile별 매핑 상수 유지.
6. research_coverage VALUATION 축을 스냅샷 집계로 전환 (PRICE 축
   패턴).

## Test

설계 문서 Test 절을 그대로 따른다. `tests/test_valuation.py` 재작성,
`tests/test_valuation_ingestion.py` 신규,
`tests/test_research_coverage.py`·`tests/test_api_contract.py`·
`tests/test_price_ingestion.py` 갱신. id 리터럴 단언 금지, 수치 단언은
픽스처 출처 주석.

## Out of Scope

- #280·#281 범위, schema.py, 가격·뉴스 수집 로직, 다른 도메인.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)
  불변.

## Rules

- 현재 브랜치 `feat/279-valuation-real-collection`에서 그대로 작업한다.
  새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
- alembic 단일 헤드 확인: `uv run alembic heads`
