# Codex Handoff Task

## Source

이슈 #230 — yfinance 실데이터 전환. 설계:
`docs/designs/230-yfinance-real-providers.md` (먼저 전체를 읽는다).

## Task Summary

`MARKET_PROVIDER=yfinance` 전환 시 깨지는 시세·지수·환율 경로를
구현하고 Redis TTL 캐시를 얹는다. **API 계약·FE·마이그레이션 없음,
`base.py` 시그니처·mock·소비 서비스 변경 금지.** 설계 문서 1~3절을
그대로 따른다:

1. `YFinanceMarketDataProvider`(fast_info 기반, 숫자 심볼 `.KS`
   휴리스틱, name은 심볼 그대로, optional은 market_cap·52주만) ·
   `YFinanceIndexQuoteProvider`(내부 심볼 유지, `SPX→^GSPC,
   IXIC→^IXIC, KOSPI→^KS11, VIX→^VIX`) ·
   `YFinanceExchangeRateProvider`(`USD/KRW→KRW=X`). 개별 심볼 실패는
   로그 후 스킵. 값 변환은 순수 함수 분리.
2. `app/adapters/market/cache.py` — `fetch_json_cached` +
   캐시 래퍼 3종(TTL: quote 60 · index 60 · fx 300, Redis 예외 시
   loader 폴백, Decimal·datetime 왕복 직렬화).
3. factory 3개 함수에 yfinance 분기(캐시 래퍼로 감쌈), mock 분기
   유지.

## Test

설계 문서 Test 절을 그대로 따른다. `tests/test_market_cache.py`
신규, `tests/test_providers.py` 갱신. yfinance `Ticker`·redis는
monkeypatch stub — 네트워크·실 Redis 금지. 수치 단언은 픽스처 출처
주석, id 리터럴 단언 금지.

## Out of Scope

- `get_quote` 시그니처 확장, per·target 실데이터, intraday 캐시,
  `.env` 전환.
- `docs/designs/266-research-queue-contract.md`(추적되지 않는 파일)
  불변.

## Rules

- 현재 브랜치 `feat/230-yfinance-real-providers`에서 그대로
  작업한다. 새 브랜치를 만들지 않는다.
- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
