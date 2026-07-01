# 061 · 시장 지수 시세 요약 (Market Index Quotes)

Status: Accepted
작성: Claude Code (orchestrator)
관련: BE #154, FE #87(사이드바 시장 요약 카드), 설계 price-series-api.md(종목 가격 시계열)

## 1. 배경

대시보드 사이드바의 "시장 요약 카드"는 S&P 500·NASDAQ·KOSPI·VIX 등 대표 지수의 현재값과
등락률을 표시합니다(FE 이슈 #87). 현재 BE에는 개별 종목 시세(`GET /stocks/{symbol}/prices`,
`GET /assets/{asset_id}/detail`)는 있으나 시장 지수를 조회하는 엔드포인트가 없습니다.

지수 조회는 asset_id 기반이 아니라 고정 지수 코드 집합에 대한 일괄 응답이 적합합니다.
LLM은 관여하지 않으며, 본 엔드포인트는 순수 시세 스냅샷 조회입니다.

두 가지 핵심 결정을 아래에서 확정합니다.

- **데이터 소스**: mock 우선 + provider seam(선택지 A). 외부 provider는 후속.
- **지수 코드 집합 정의 위치**: adapter 계층 상수로 고정.

## 2. 범위

포함:

- 시장 지수 응답 스키마 `MarketIndexQuoteResponse`.
- adapter dataclass `IndexQuoteResult` + `IndexQuoteProvider` 인터페이스 + `MockIndexQuoteProvider` 구현.
- factory `get_index_quote_provider()`.
- `MarketIndexService` 서비스.
- 신규 API 엔드포인트 `GET /market/indices`.
- 대표 지수 코드 집합 상수 정의.

비포함(분리):

- 외부 실시간 시세 provider 연동 — 후속 이슈, 연동 시 ADR 신규.
- 지수 시계열(봉 데이터) — 본 설계는 현재값 스냅샷만 반환합니다.
- 지수별 상세 종목 구성(ETF 매핑 등) — 본 범위 밖.
- 지수별 필터 파라미터(`?symbols=...`) — 현 단계는 전체 반환.
- 단기 TTL 캐시 — 외부 provider 연동 시점에 검토.

## 3. adapter 계층 (seam)

기존 `MarketDataProvider`/`PriceSeriesProvider`와 동일하게, adapter는 Pydantic이 아닌
frozen `@dataclass`를 반환합니다. 응답 스키마 매핑은 서비스 책임입니다.

`IndexQuoteResult`(frozen dataclass, 위치 `app/adapters/market/base.py`):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| symbol | str | 지수 코드 (예: `SPX`, `IXIC`, `KOSPI`, `VIX`) |
| name | str | 표시 이름 (예: `S&P 500`) |
| value | Decimal | 현재값 (지수 단위, 통화 아님) |
| change_percent | Decimal | 전일 대비 변동률 (%, 부호 포함) |
| reference_at | datetime | 기준 시각 (tz-aware UTC) |

```
class IndexQuoteProvider(ABC):
    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]: ...
```

`MockIndexQuoteProvider`(위치 `app/adapters/market/mock.py`):

```
class MockIndexQuoteProvider(IndexQuoteProvider):
    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]: ...
```

구현 지침:

- 지수 코드별로 seed 기반 결정론적 값을 생성합니다(테스트 재현성). 기존 mock의 `sha256`
  기반 fallback 패턴을 참고합니다.
- `reference_at`은 기존 mock의 `_AS_OF`(고정 UTC 시각)와 동일한 결정론적 기준 시각을 씁니다
  (요청 시각 사용 금지 — 테스트 재현성 확보).
- 인터페이스 이름은 종목 quote(`MarketDataProvider`)와 충돌하지 않도록 `IndexQuoteProvider`로
  분리합니다.

## 4. 응답 스키마

`MarketIndexQuoteResponse(BaseModel)`(위치 `app/domains/market/schema.py`):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| symbol | str | 지수 코드 |
| name | str | 표시 이름 |
| value | Decimal | 현재값 (C5 컨벤션대로 Decimal, JSON 문자열 직렬화) |
| change_percent | Decimal | 전일 대비 변동률 (%) |
| reference_at | UtcDatetime | 기준 시각(UTC) |

API 응답: `ApiResponse[list[MarketIndexQuoteResponse]]` — 공통 envelope 준수.

`value`는 지수 단위이므로 통화가 아니며 Decimal로 직렬화합니다. `change_percent`는 부호
포함 비율입니다(예: `-1.23`).

## 5. 지수 코드 집합 (확정: adapter 상수)

조회 대상 지수 코드는 adapter 계층 상수로 고정합니다(변경 빈도가 낮아 설정 외부화 불요).
위치는 `app/adapters/market/mock.py`(mock 값과 함께) 또는 별도 상수 모듈 — 핸드오프 시
구현자가 기존 mock 구성에 맞춰 배치합니다. 4개 지수:

| symbol | name | 비고 |
| --- | --- | --- |
| SPX | S&P 500 | 소수점 2자리 |
| IXIC | NASDAQ Composite | 소수점 2자리 |
| KOSPI | KOSPI | 소수점 2자리 |
| VIX | VIX | 소수점 2자리 |

## 6. 서비스

신규 `app/domains/market/index_service.py`:

```
class MarketIndexService:
    def get_quotes(self) -> list[MarketIndexQuoteResponse]: ...
```

`get_quotes` 책임:

- 고정 지수 코드 집합을 `get_index_quote_provider().get_quotes(...)`에 전달합니다(factory를
  서비스 내부에서 호출 — 기존 `PriceSeriesService`가 `get_price_series_provider()`를 내부
  호출하는 패턴과 동일).
- provider가 반환한 `IndexQuoteResult` 리스트를 `MarketIndexQuoteResponse`로 매핑합니다.
- provider 호출을 `try/except`로 감싸 실패 시 `AppException(status_code=502,
  error_code=MARKET_DATA_PROVIDER_ERROR)`를 던집니다(기존 `PriceSeriesService`와 동일 규칙).

DB·repository는 사용하지 않습니다(스냅샷 조회, 영속화 없음).

## 7. API

신규 라우터 파일 `app/api/v1/endpoints/market.py`, `app/api/v1/router.py`에 `/market`
prefix로 등록:

| Method | Path | 응답 | 비고 |
| --- | --- | --- | --- |
| GET | `/market/indices` | `list[MarketIndexQuoteResponse]` | 공통 envelope, 인증 불요 |

- 인증: 시장 지수는 공개 정보이므로 인증 없이 접근 가능합니다(`get_current_user` 미의존).
- 파라미터: 현 단계 없음(전체 지수 반환).
- 에러: provider 오류 시 502(`MARKET_DATA_PROVIDER_ERROR`).

## 8. factory

`app/adapters/factory.py`에 `get_index_quote_provider()`를 추가합니다. 기존
`get_market_provider()`/`get_price_series_provider()`와 동일하게 `MARKET_PROVIDER` 스위치를
재사용합니다:

```
def get_index_quote_provider() -> IndexQuoteProvider:
    if settings.MARKET_PROVIDER == "mock":
        return MockIndexQuoteProvider()
    raise NotImplementedError("market real provider 미구현")
```

## 9. 의존성

- `app/adapters/market/base.py`(`IndexQuoteResult`·`IndexQuoteProvider`) — 신규 추가.
- `app/adapters/market/mock.py`(`MockIndexQuoteProvider`·지수 상수) — 신규 추가.
- `app/adapters/factory.py`(`get_index_quote_provider`) — 신규 추가, `MARKET_PROVIDER` 재사용.
- `app/domains/market/`(`schema.py`·`index_service.py`) — 신규 도메인.
- `app/core/response.py`(`ApiResponse`·`success`) — 그대로 사용.
- `app/core/error_codes.py`(`MARKET_DATA_PROVIDER_ERROR`) — 기존 코드 재사용(확인 완료).
- `app/core/schema.py`(`UtcDatetime`) — 재사용.
- `app/api/v1/router.py` — `/market` prefix 신규 라우터 등록.

## 10. 테스트

- provider 단위: `MockIndexQuoteProvider.get_quotes`가 정의된 지수 코드 수(4)만큼 항목을
  반환하고, 각 항목의 필드 타입(`value`·`change_percent`가 Decimal, `reference_at`이 tz-aware)을
  단언합니다. 동일 입력 재호출 시 값이 결정론적으로 동일함을 단언합니다.
- 서비스: provider가 반환한 dataclass가 `MarketIndexQuoteResponse`로 매핑됨을 단언합니다.
  provider 오류 주입 시 502(`MARKET_DATA_PROVIDER_ERROR`) 발생을 단언합니다.
- API: `GET /market/indices` 응답 형태(envelope·fields)·상태 코드 200, 인증 없이 접근
  가능함을 단언합니다.
- 계약 스냅샷: `MarketIndexQuoteResponse` 스키마를 `tests/test_api_contract.py`에 반영합니다.

## 11. 문서·ADR 영향

- ADR 불요: mock 우선 + 기존 `MARKET_PROVIDER` seam 재사용으로 신규 외부 의존성·아키텍처
  변경 없음. 외부 provider 연동 시점에 ADR 신규.
- 실패기록 불요: 국소 신규 endpoint, provider 오류는 502로 커버.
