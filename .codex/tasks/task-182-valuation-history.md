# Codex Handoff Task

## Source

이슈 #281 — 5년 배수 히스토리 산출. 설계:
`docs/designs/281-valuation-history-derivation.md` (먼저 전체를 읽는다).

## Task Summary

`valuation-metrics`의 `five_year_median`·`percentile`을 실파생으로
전환한다. **API 계약(`app/domains/valuation/schema.py`)은 변경하지
않고, 이번 라운드에 alembic 마이그레이션은 없다.** 설계 문서 1~3절을
그대로 따른다:

1. 가격 range 관통 — `_range_to_period`에 `"5Y"` 추가(yfinance·mock),
   `PriceIngestionService.collect_and_save`와 `collect_prices_job`에
   `range_value: str = "3M"` 파라미터 추가 (기존 호출 동작 불변).
2. `app/domains/valuation/history.py` 신규 — 순수 함수 3개:
   `build_ttm_eps_series`(연속 4행 슬라이딩 윈도, eps null 윈도 스킵),
   `build_per_series`(period_end ≤ 종가일 최근 TTM 매칭, TTM 0 이하
   제외), `median_and_percentile`(관측치 20 미만 None, 중앙값 quantize
   0.01, 백분위 = 시계열 마지막 값의 순위 비율 0~100 int 반올림).
3. `ValuationService.get_metrics` — 최근 5년 종가(`get_daily_closes`)와
   최근 8분기(`get_recent`)로 **PER metric 행에만** median·percentile을
   채운다. 나머지 6종과 산출 불가 시에는 null 유지.

## Test

설계 문서 Test 절을 그대로 따른다. `tests/test_valuation_history.py`
신규, `tests/test_valuation.py`·`tests/test_price_ingestion.py` 갱신,
필요 시 `tests/test_api_contract.py`. 수치 단언은 픽스처 출처 주석,
id 리터럴 단언 금지.

## Out of Scope

- PER 외 6종 히스토리, 사전 계산 테이블, 백필 자동화, #282 범위.
- `app/domains/valuation/schema.py`·`model.py`, earnings·prices
  repository 시그니처, 다른 도메인.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)
  불변.

## Rules

- 현재 브랜치 `feat/281-valuation-history`에서 그대로 작업한다.
  새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
