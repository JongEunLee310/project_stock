# 031 Asset Basic Info API

## Scope

종목 상세 상단 카드에 필요한 기본 정보와 현재 mock 시세를 단건 API로 제공한다.

## Data Model

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `sector` | `String(100)` | No | 후속 포트폴리오 섹터 비중에서 재사용 가능 |
| `industry` | `String(100)` | No | 상세 카드 표시용 |
| `description` | `Text` | No | 종목 설명 |

## API

`GET /api/v1/assets/{asset_id}/detail`

- Auth: Not required
- Response fields: `id`, `symbol`, `name`, `market`, `price`, `previous_close`, `change`, `change_percent`, `currency`, `sector`, `industry`, `description`, `as_of`
- Quote source: `get_market_provider().get_quote([symbol])`
- Missing asset: `404 ASSET_NOT_FOUND`

## Decisions

- 기존 `GET /api/v1/assets/{asset_id}` response shape is unchanged.
- Decimal quote fields are exposed as strings to match existing JSON conventions.
