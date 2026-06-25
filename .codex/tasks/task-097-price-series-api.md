# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#97 — [계약정렬] 가격 시계열 API OHLCV 신설 (G4/N4)
설계 기준 문서: `docs/designs/price-series-api.md` (§ 계약 확정 — 2026-06-25, Opus)

## Task Summary

종목 일봉 OHLCV 가격 시계열 조회 API(`GET /api/v1/stocks/{symbol}/prices`)를 신설한다. MockPriceSeriesProvider가 결정론적 OHLCV를 생성하고, `stock_price_bars` 테이블에 idempotent upsert 후 DB에서 조회해 응답한다. FE 차트·Signal 모멘텀 시각화의 선행(N4).

## Goal

완료 시 다음이 참이어야 한다:
- `GET /api/v1/stocks/{symbol}/prices?market=&range=&interval=&adjusted=` 가 `docs/designs/price-series-api.md`의 확정 계약대로 응답한다.
- `stock_price_bars` 테이블과 Alembic 마이그레이션이 생성되고 `alembic upgrade head` 가 통과한다.
- Mock provider가 결정론적(symbol 시드)으로 OHLCV를 생성하고, 서비스가 테이블에 upsert 후 조회해 응답한다(빈 테이블 아님).
- 신규 에러 코드 4종이 명세된 HTTP 상태로 매핑된다.
- 전체 테스트 통과(신규 테스트 포함), `TZ=UTC` 에서 날짜 경계 단언 통과.

## Background

- 와이어 컨벤션: snake_case 필드, 금액=Decimal **문자열**, 시각=`app/core/schema.py`의 `UtcDatetime`(`...Z`), 공통 엔벨로프 `app/core/response.py`의 `ApiResponse`/`success`. 참고 구현: `app/domains/assets/schema.py`(price: str 패턴), `app/domains/assets/model.py`(UniqueConstraint/Base/TimestampMixin).
- Provider 스위치: 기존 `app/core/config.py`의 `MARKET_PROVIDER`(mock/real) 재사용. 별도 env 추가 금지.
- 도메인 구조는 기존 패턴(model/repository/service/schema + router)을 따른다.
- **타임존 결정(중요)**: 일봉은 캘린더 날짜다. 테이블 `timestamp`는 거래일 **00:00:00+00(UTC 자정)** 으로 저장하고, 와이어 `bars[].date`는 그 `timestamp`의 **UTC 날짜부분**(`YYYY-MM-DD`, 타임존 없는 문자열)로 낸다. KST 변환 절대 금지(오프바이원 차단).

## Implementation Scope

- 신규 도메인 `app/domains/prices/`: `model.py`(StockPriceBar), `repository.py`(upsert·range 조회), `service.py`, `schema.py`(PriceSeriesResponse, PriceBar).
- 라우터: `app/api/v1` 에 prices 라우터 등록(`GET /stocks/{symbol}/prices`). 기존 v1 라우터 등록 방식과 동일하게 연결.
- Provider: `app/adapters/market/base.py` 에 `PriceSeriesProvider`(ABC), `app/adapters/market/mock.py` 에 `MockPriceSeriesProvider`. 기존 provider 팩토리/선택 지점에 price series provider 추가(`MARKET_PROVIDER` 재사용).
- 에러코드: `app/core/error_codes.py` 에 `INVALID_PRICE_RANGE`, `INVALID_PRICE_INTERVAL`, `PRICE_SERIES_NOT_FOUND`, `MARKET_DATA_PROVIDER_ERROR` 추가. 라우터/서비스에서 명세 HTTP 상태로 매핑.
- 마이그레이션: `alembic/versions/` 신규 리비전(`stock_price_bars`). down_revision은 현재 head 확인 후 연결.

## Out of Scope

- 실 외부 시세 API 연동, 분봉/실시간, 다중 종목 비교, 수익률 정규화, 이동평균, 캐시 전략(모두 후속).
- assets soft-validate(미등록 symbol도 조회 허용 — MVP는 검증 안 함).
- 기존 도메인 스키마/엔드포인트 변경. FE 코드.
- `docs/api/*` 스펙 스냅샷 갱신(별도 spec 통합 라운드에서 Opus가 처리).

## Protected Files

없음. `.codex/*`, `.claude/*`, `docs/harness/*`, `docs/decisions/*` 수정 금지.

## Requirements

- 쿼리: `market`(필수, KRX|NASDAQ|NYSE), `range`(기본 3M, 1M|3M|6M|1Y), `interval`(기본 1d, 1d 외 INVALID_PRICE_INTERVAL), `adjusted`(기본 true).
- 응답 `data`: `symbol, market, currency, interval, range, source, last_updated_at(UtcDatetime), bars[]`. `bars[]`: `date(YYYY-MM-DD 문자열), open, high, low, close, adjusted_close(모두 Decimal 문자열), volume(정수)`. 오름차순. 페이지네이션 없음(`meta=null`).
- `adjusted=false` 시 mock은 `adjusted_close == close`.
- range→봉 개수 근사: 1M≈22, 3M≈66, 6M≈132, 1Y≈252 영업일.
- 에러 매핑: INVALID_PRICE_RANGE=400, INVALID_PRICE_INTERVAL=400, PRICE_SERIES_NOT_FOUND=404, MARKET_DATA_PROVIDER_ERROR=502, 필수 누락=기존 VALIDATION_ERROR(422).
- Numeric(20,4), volume BigInteger, UniqueConstraint(symbol, market, interval, timestamp) 이름 `uq_price_bars_symbol_market_interval_ts`.
- 서비스는 provider 생성분을 테이블에 idempotent upsert(중복 유니크키는 갱신/무시) 후 DB 조회로 응답.

## Test Requirements

- 라우터 통합 테스트(전용 신규 파일): 정상 응답 구조·필드 표기(snake_case)·Decimal 문자열·date 형식, 각 에러코드별 상태, range/interval 검증, adjusted 동작.
- 날짜 경계 테스트는 `TZ=UTC` 로 수행하고 mock 생성 거래일과 응답 `date` 1:1 단언(오프바이원 회귀 방지).
- repository upsert 멱등성(같은 키 2회 요청 시 행 중복 없음) 테스트.
- 기존 테스트 무손상.

## Verification Commands

```
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run alembic upgrade head
TZ=UTC uv run pytest
```

## Documentation Impact

- `docs/designs/price-series-api.md` 는 확정본이므로 수정 불필요(구현이 이 문서를 따른다).
- `docs/api/*` 스펙 스냅샷은 Out of Scope(후속 Opus 처리).

## ADR Need

불필요. 기존 패턴(도메인 구조·provider 스위치·엔벨로프) 내 신규 기능이며 새 아키텍처 결정 없음.

## Failure Record Need

불필요(현재 예상되는 실패 없음). 구현 중 sandbox/마이그레이션 충돌 발생 시 보고만.

## Risk Level

Medium — 신규 테이블/마이그레이션(DB 스키마) 포함. **DB 스키마는 human-gate 대상**으로, 본 task는 사람 승인 후에만 실행한다(ADR-005 #6).

## Expected Output

- 신규 도메인·provider·에러코드·마이그레이션·테스트 포함 브랜치 + PR.
- 모든 검증 명령 통과(특히 `alembic upgrade head`, `TZ=UTC pytest`).
- PR 본문에 BE#97 라벨 승계(api, frontend-integration, market-data, priority:high).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- `--dangerously-bypass-approvals-and-sandbox` / `-s danger-full-access` 사용 금지(ADR-005).
