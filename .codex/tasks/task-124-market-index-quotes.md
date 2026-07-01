# Codex Handoff Task

## Source Issue

BE #154 (시장 지수 시세 endpoint), FE #87(사이드바 시장 요약 카드). 설계: `docs/designs/061-market-index-quotes.md`.

## Task Summary

대시보드 사이드바 "시장 요약 카드"에 실데이터를 공급하기 위해 대표 시장 지수(S&P 500·NASDAQ·KOSPI·VIX)의 현재값·등락률을 반환하는 `GET /market/indices` endpoint를 추가한다. mock 우선 + provider seam 구조로, 외부 실시간 연동은 후속 이슈로 분리한다.

## Goal

완료 시 다음이 참이어야 한다.

- `GET /api/v1/market/indices`가 인증 없이 200과 공통 envelope(`ApiResponse[list[MarketIndexQuoteResponse]]`)로 4개 지수 시세를 반환한다.
- adapter가 frozen `@dataclass`(`IndexQuoteResult`)를 반환하고 서비스가 응답 스키마로 매핑하는 기존 seam 관례를 따른다.
- provider 오류 시 502(`MARKET_DATA_PROVIDER_ERROR`)를 반환한다.
- `MARKET_PROVIDER` 스위치를 재사용하는 factory `get_index_quote_provider()`가 mock을 반환한다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- 설계 확정본 `docs/designs/061-market-index-quotes.md`를 그대로 따른다. 열린 결정은 설계에서 이미 확정됐다(데이터 소스=mock 우선, 지수 코드 집합=adapter 상수).
- 기존 seam 관례(반드시 준수):
  - adapter는 Pydantic이 아닌 frozen `@dataclass`를 반환한다(`app/adapters/market/base.py`의 `QuoteResult`·`PriceBarResult` 참고).
  - mock provider는 결정론적 값을 반환한다(`app/adapters/market/mock.py`의 `_AS_OF` 고정 시각·`sha256` 기반 fallback 참고). 요청 시각을 쓰지 말 것 — 테스트 재현성.
  - 서비스가 factory를 내부 호출하고 provider 오류를 `try/except`로 감싸 502로 던진다(`app/domains/prices/service.py`의 `PriceSeriesService.get_series` 패턴과 동일).
- `MARKET_DATA_PROVIDER_ERROR`는 `app/core/error_codes.py`에 이미 존재한다(재사용).
- 지수 조회는 스냅샷이므로 DB·repository·마이그레이션이 없다.

## Implementation Scope

Codex가 변경할 수 있는 파일·동작:

- `app/adapters/market/base.py` — `IndexQuoteResult`(frozen dataclass)·`IndexQuoteProvider`(ABC) 추가.
- `app/adapters/market/mock.py` — `MockIndexQuoteProvider` + 4개 지수 상수(SPX·IXIC·KOSPI·VIX) 추가.
- `app/adapters/factory.py` — `get_index_quote_provider()` 추가(`MARKET_PROVIDER` 스위치 재사용).
- `app/domains/market/__init__.py`·`schema.py`·`index_service.py` — 신규 도메인. `MarketIndexQuoteResponse` 스키마와 `MarketIndexService.get_quotes()`.
- `app/api/v1/endpoints/market.py` — 신규 라우터. `GET /indices`.
- `app/api/v1/router.py` — `/market` prefix로 라우터 등록.
- `tests/` — 아래 Test Requirements 참고.

## Out of Scope

- 외부 실시간 provider 연동(선택지 B) — 후속 이슈. `MARKET_PROVIDER == "real"` 분기는 기존 패턴대로 `NotImplementedError`.
- 지수 시계열(봉 데이터), 지수별 종목 구성.
- 필터 파라미터(`?symbols=...`), 캐시(TTL) 도입.
- 인증 부착(지수는 공개 정보 — `get_current_user` 미의존).
- 종목 quote(`MarketDataProvider`) 관련 코드 변경 — 이름 충돌만 피하고 건드리지 않는다.

## Protected Files

없음. 위 Implementation Scope 밖 파일은 변경하지 않는다.

## Requirements

- `IndexQuoteResult` 필드: `symbol: str`, `name: str`, `value: Decimal`, `change_percent: Decimal`, `reference_at: datetime`(tz-aware UTC).
- `MarketIndexQuoteResponse` 필드: `symbol: str`, `name: str`, `value: Decimal`, `change_percent: Decimal`, `reference_at: UtcDatetime`.
- `IndexQuoteProvider.get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]`.
- 지수 코드 집합은 adapter 계층 상수로 고정: SPX(S&P 500)·IXIC(NASDAQ Composite)·KOSPI(KOSPI)·VIX(VIX).
- `MarketIndexService.get_quotes()`는 고정 코드 집합을 provider에 전달하고 dataclass→응답 스키마로 매핑한다. provider 오류 시 `AppException(status_code=502, error_code=ErrorCode.MARKET_DATA_PROVIDER_ERROR)`.
- 엔드포인트는 `success(...)`로 envelope을 감싼다.

## Test Requirements

- provider 단위: `get_quotes`가 4개 항목 반환, 각 필드 타입(`value`·`change_percent`=Decimal, `reference_at` tz-aware) 단언, 재호출 시 결정론적 동일값 단언.
- 서비스: dataclass→`MarketIndexQuoteResponse` 매핑 단언, provider 오류 주입 시 502(`MARKET_DATA_PROVIDER_ERROR`) 단언.
- API: `GET /api/v1/market/indices` 200·envelope·필드, 인증 없이 접근 가능 단언.
- 계약 스냅샷: `tests/test_api_contract.py`에 `MarketIndexQuoteResponse` 스키마 반영.

## Verification Commands

```
uv run ruff check .
uv run mypy app
uv run pytest
```

세 검사 모두 통과해야 한다. mypy 누락 금지.

## Documentation Impact

- `docs/designs/061-market-index-quotes.md` — 설계 확정본(이미 브랜치에 포함). 구현이 설계와 어긋나면 구현이 아니라 보고로 처리.
- `.codex/tasks/task-124-market-index-quotes.md` — 본 핸드오프 기록.

## ADR Need

불요. mock 우선 + 기존 `MARKET_PROVIDER` seam 재사용으로 신규 외부 의존성·아키텍처 변경 없음. 외부 provider 연동 시점에 ADR 신규.

## Failure Record Need

불요. 국소 신규 endpoint, provider 오류는 502로 커버.

## Risk Level

Low. 신규 파일 위주, DB·마이그레이션 없음, 기존 seam·에러 코드·envelope 재사용.

## Expected Output

- 위 Implementation Scope 파일 변경 + 테스트.
- 검증 3종 통과 로그.
- 설계와의 차이·가정이 있으면 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
