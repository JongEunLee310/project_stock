# 034 Portfolio Summary API

## Scope

대시보드에서 보유 종목·비중을 확인할 수 있도록 기존 포트폴리오 요약을 확장한다. 시세(mock) 기반 평가금액, 섹터별 비중, 현금 비중, 섹터 쏠림 여부를 추가한다. 손익/수익률, 실시간 외부 시세, 자동 리밸런싱은 포함하지 않는다.

## Data Model

기존 `portfolios` 테이블에 현금 잔액 컬럼을 추가한다.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `cash_balance` | `Numeric` | Yes | 기본값 `0`, server_default. 평가금액/현금 비중 산출에 사용 |

종목·섹터 비중은 영속하지 않고 조회 시 계산한다. `Asset.sector`(nullable) 사용, null은 `UNKNOWN` 그룹으로 집계.

## API

`GET /api/v1/portfolios/{portfolio_id}/summary` (기존 엔드포인트 확장)

- Auth: Required (본인 포트폴리오만)
- Response 추가 필드:
  - `total_value`: 총 평가금액 = Σ(quantity × mock 시세 price) + cash_balance
  - `positions[].market_value`, `positions[].weight`: 시세 기반 평가금액·비중
  - `sector_weights`: 섹터별 비중 목록 `{sector, weight, exceeds_threshold}`
  - `cash_weight`: 현금 비중
  - `positions[].exceeds_threshold`: 종목 과다 비중 여부 (기존)
  - 섹터 쏠림 여부: 섹터 비중이 임계치 초과 시 표시

## Functions

- `PortfolioService._build_summary(portfolio)` — 시세 평가금액·섹터 집계·현금 비중·쏠림 판정을 포함하도록 확장.
- 시세 조회: `get_market_provider().get_quote(symbols)` (mock, 결정적). 외부 키 불필요.

## Decisions

- 평가금액은 mock provider 시세 기반으로 결정적 — 테스트 안정성 확보.
- 섹터 쏠림 임계치는 별도 컬럼을 추가하지 않고 기존 `concentration_threshold`를 재사용한다.
- 현금은 영속 필드(`cash_balance`)로 모델링 — 추후 손익 계산 확장 여지를 남기되 현재 범위는 비중 산출에 한정.
- 비중 합(종목 + 현금)은 반올림 오차 내 1에 수렴.
