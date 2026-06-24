# Frontend API Spec

이 문서는 프론트엔드 주요 화면에서 사용할 현재 구현 API를 화면 단위로 정리한다.
모든 `/api/v1` API 응답은 별도 표기가 없는 한 공통 envelope를 사용한다.

```json
{
  "data": {},
  "message": null,
  "error": null,
  "meta": null
}
```

목록 응답은 `meta`에 `{ "page": 1, "size": 20, "total": 1 }`을 포함한다. 실패 응답은 `data: null`, `meta: null`이며 `error.code`에는 `ErrorCode` 문자열이 들어간다. `/health`, `/api/v1/health`, `/api/v1/health/readiness`는 모니터링 호환을 위해 envelope를 사용하지 않는다.

## Datetime 규약

모든 API 응답의 datetime 필드는 UTC, ISO 8601 `Z` 표기로 직렬화된다(예: `"2026-06-19T00:00:00Z"`). DB에서 timezone 정보 없이 반환되는 naive datetime은 UTC로 간주하여 처리한다. FE는 표시 시 필요에 따라 KST(UTC+9)로 변환한다.

## Common List Query Rules

목록 API는 공통 페이지네이션 query를 사용한다. `page`는 `1` 이상이고 기본값은
`1`, `size`는 `1..100`이고 기본값은 `20`이다. 목록 응답의 `meta`는 항상
요청된 `page`/`size`와 전체 건수 `total`을 포함한다.

정렬을 지원하는 목록은 `sort`에 단일 필드를 받는다. `field`는 오름차순,
`-field`는 내림차순이며, 허용되지 않은 필드는 `422 VALIDATION_ERROR`로 거부된다.
필터는 리소스별 typed query parameter를 사용한다.

## Contract 변경 검토 기준

프론트엔드가 직접 연동하는 응답 contract 변경은 의도적 변경으로 간주한다. 다음
변경은 반드시 `tests/test_api_contract.py`와 이 문서를 함께 갱신한다.

- 공통 envelope의 `data`, `message`, `error`, `meta` 키 변경
- 목록 응답의 `meta.page`, `meta.size`, `meta.total` 키 또는 타입 변경
- 프론트 직접 연동 API의 `data` 필수 필드 추가, 삭제, 이름 변경, 타입 변경
- nullable 여부 변경, 배열 item 구조 변경, enum/string 값 범위 변경
- OpenAPI path, response schema, 인증 필요 여부 변경

응답 값의 구체적인 숫자, 날짜, mock 데이터 내용은 contract가 아니라 동작 테스트
대상이다. contract 테스트는 필수 키와 타입만 고정한다.

## 프론트 영향 범위 확인 절차

contract 변경 PR은 다음 순서로 영향 범위를 확인한다.

1. 이 문서의 Screen Map에서 변경 path를 사용하는 화면을 찾는다.
2. `Implemented API Catalog`의 요청/응답 예시와 인증 여부를 변경 내용에 맞춘다.
3. `tests/test_api_contract.py`의 필수 필드·타입 기대값을 의도한 contract로 갱신한다.
4. `/openapi.json` 또는 `app.openapi()`에서 path와 response component가 남아 있는지 확인한다.
5. 변경된 화면, 필드, 마이그레이션 필요 여부를 PR 본문에 적고 프론트엔드 확인을 요청한다.

## Auth

인증 필요 API는 `Authorization: Bearer <access_token>` 헤더가 필요하다.

대표 인증 실패:

```json
{
  "data": null,
  "message": "유효하지 않은 토큰입니다.",
  "error": { "code": "AUTH_INVALID_TOKEN" },
  "meta": null
}
```

대표 validation 실패:

```json
{
  "data": null,
  "message": "요청 값이 올바르지 않습니다.",
  "error": {
    "code": "VALIDATION_ERROR",
    "fields": [{ "loc": ["body", "email"], "msg": "value is not a valid email address" }]
  },
  "meta": null
}
```

## Frontend Dev Environment

브라우저 기반 프론트엔드에서 API를 호출할 때 허용 origin은 백엔드 환경 변수
`CORS_ORIGINS`로 주입한다. 로컬 개발 예시는
`http://localhost:3000,http://localhost:5173`이고, 운영에서는 배포된 프론트엔드
도메인만 명시한다.

`CORS_ALLOW_CREDENTIALS` 기본값은 `false`다. 쿠키 기반 인증 등 credential 동반
요청이 필요해지면 `CORS_ORIGINS=*`를 사용할 수 없고 명시 origin 목록을 설정해야
한다. `OPTIONS` preflight 요청은 FastAPI CORS middleware가 처리한다.

## Screen Map

### 대시보드

| Purpose | Method | Path | Auth | Notes |
| --- | --- | --- | --- | --- |
| 알림 후보/시그널 요약 | `GET` | `/api/v1/signals?asset_id={asset_id}&include_expired=false&page=1&size=20` | Required | 현재 asset 단위 조회. 전체 대시보드 집계 API는 미구현 후보. |
| 포트폴리오 목록 | `GET` | `/api/v1/portfolios?page=1&size=20` | Required | 요약 조회 전 선택 목록. |
| 포트폴리오 요약 | `GET` | `/api/v1/portfolios/{portfolio_id}/summary` | Required | 집중도/비중 표시. |
| 관심종목 목록 | `GET` | `/api/v1/watchlists?page=1&size=20` | Required | 사용자 관심종목 그룹 목록. |
| 관심종목 항목 | `GET` | `/api/v1/watchlists/{watchlist_id}/items?page=1&size=20&sort=priority` | Required | 항목별 사유/태그/메모 표시. |
| 알림 목록 | `GET` | `/api/v1/alerts?status=UNREAD&page=1&size=20` | Required | unread 카드/배지 표시. |
| 알림 후보 | `GET` | `/api/v1/alert-candidates?status=UNREAD&page=1&size=20&sort=-created_at` | Required | 발송 전 후보 검토. |

### 관심종목

| Purpose | Method | Path | Auth |
| --- | --- | --- | --- |
| 목록 조회 | `GET` | `/api/v1/watchlists?page=1&size=20` | Required |
| 관심목록 생성 | `POST` | `/api/v1/watchlists` | Required |
| 관심종목 항목 조회 | `GET` | `/api/v1/watchlists/{watchlist_id}/items?page=1&size=20&sort=priority` | Required |
| 관심종목 추가 | `POST` | `/api/v1/watchlists/{watchlist_id}/items` | Required |
| 관심종목 제거 | `DELETE` | `/api/v1/watchlists/{watchlist_id}/items/{item_id}` | Required |

### 종목상세

| Purpose | Method | Path | Auth |
| --- | --- | --- | --- |
| 종목 정보 | `GET` | `/api/v1/assets/{asset_id}` | Not required |
| 종목 기본 정보 카드 | `GET` | `/api/v1/assets/{asset_id}/detail` | Not required |
| 최신 투자 가설 | `GET` | `/api/v1/theses/latest?asset_id={asset_id}` | Required |
| 리서치 요약 | `GET` | `/api/v1/assets/{asset_id}/research-summary` | Required |
| 매수 전 점검 | `GET/PUT` | `/api/v1/assets/{asset_id}/buy-checklist` | Required |
| 리서치 리포트 목록 | `GET` | `/api/v1/reports?asset_id={asset_id}&page=1&size=20` | Required |
| 시그널 목록 | `GET` | `/api/v1/signals?asset_id={asset_id}&include_expired=false&page=1&size=20` | Required |

### 리서치요약

| Purpose | Method | Path | Auth | Notes |
| --- | --- | --- | --- | --- |
| 리포트 목록 | `GET` | `/api/v1/reports?asset_id={asset_id}&page=1&size=20` | Required | thesis conflict 필드는 report payload에 포함. |
| 종목 요약 카드 | `GET` | `/api/v1/assets/{asset_id}/research-summary` | Required | Mock 요약. |
| 리포트 상세 | `GET` | `/api/v1/reports/{report_id}` | Required | 요약/근거/위험 수준 표시. |
| 리포트 생성 | `POST` | `/api/v1/reports` | Required | 운영/관리성 생성 API. |
| 가설 생성/수정/비활성화 | `POST/PUT/PATCH` | `/api/v1/theses...` | Required | 화면 편집 기능이 필요할 때 사용. |

### 알림후보

| Purpose | Method | Path | Auth |
| --- | --- | --- | --- |
| 알림 후보 목록 | `GET` | `/api/v1/alert-candidates?status=UNREAD&page=1&size=20&sort=-created_at` | Required |
| 알림 후보 읽음 | `POST` | `/api/v1/alert-candidates/{candidate_id}/read` | Required |
| 알림 후보 확인 | `POST` | `/api/v1/alert-candidates/{candidate_id}/confirm` | Required |
| 시그널 목록 | `GET` | `/api/v1/signals?asset_id={asset_id}&include_expired=false&page=1&size=20` | Required |
| 시그널 상세 | `GET` | `/api/v1/signals/{signal_id}` | Required |
| 알림 목록 | `GET` | `/api/v1/alerts?status=UNREAD&page=1&size=20` | Required |
| 읽음 처리 | `POST` | `/api/v1/alerts/{alert_id}/read` | Required |
| 숨김 처리 | `POST` | `/api/v1/alerts/{alert_id}/dismiss` | Required |

### 포트폴리오요약

| Purpose | Method | Path | Auth |
| --- | --- | --- | --- |
| 포트폴리오 목록 | `GET` | `/api/v1/portfolios?page=1&size=20` | Required |
| 포트폴리오 생성 | `POST` | `/api/v1/portfolios` | Required |
| 요약 조회 | `GET` | `/api/v1/portfolios/{portfolio_id}/summary` | Required |
| 집중도 점검 | `POST` | `/api/v1/portfolios/{portfolio_id}/check` | Required |
| 포지션 추가/수정/삭제 | `POST/PATCH/DELETE` | `/api/v1/portfolios/{portfolio_id}/positions...` | Required |

### 설정

| Purpose | Method | Path | Auth | Notes |
| --- | --- | --- | --- | --- |
| 내 계정 조회 | `GET` | `/api/v1/auth/me` | Required | 현재 설정 화면에서 사용할 수 있는 구현 API. |
| 알림 설정 | - | - | - | 미구현 후보. v0.2 후속 이슈에서 별도 API 정의 필요. |

## Implemented API Catalog

### Auth

#### `POST /api/v1/auth/register`

- Auth: Not required
- Request:

```json
{ "email": "user@example.com", "password": "secret1234" }
```

- Success `201`:

```json
{ "data": { "id": 1, "email": "user@example.com", "is_active": true }, "message": null, "error": null, "meta": null }
```

- Representative error `400 USER_EMAIL_DUPLICATE`:

```json
{ "data": null, "message": "이미 등록된 이메일입니다.", "error": { "code": "USER_EMAIL_DUPLICATE" }, "meta": null }
```

#### `POST /api/v1/auth/login`

- Auth: Not required
- Request:

```json
{ "email": "user@example.com", "password": "secret1234" }
```

- Success `200`:

```json
{ "data": { "access_token": "jwt-token", "token_type": "bearer" }, "message": null, "error": null, "meta": null }
```

- Representative error `401 AUTH_INVALID_CREDENTIALS`:

```json
{ "data": null, "message": "이메일 또는 비밀번호가 올바르지 않습니다.", "error": { "code": "AUTH_INVALID_CREDENTIALS" }, "meta": null }
```

#### `GET /api/v1/auth/me`

- Auth: Required
- Request: none
- Success `200`:

```json
{ "data": { "id": 1, "email": "user@example.com", "is_active": true }, "message": null, "error": null, "meta": null }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

### Dashboard

#### `GET /api/v1/dashboard/summary`

- Auth: Required
- Request: none (인증 사용자 기준 집계)
- Success `200`:

```json
{ "data": { "risk_alert_count": 2, "important_news_count": 5, "review_signal_count": 3, "cash_weight": "0.18", "risk_alert_delta": null, "important_news_delta": null, "review_signal_delta": null, "cash_weight_delta": null }, "message": null, "error": null, "meta": null }
```

- 카드 집계 의미: `risk_alert_count`=미확인 위험 알림 수, `important_news_count`=중요 뉴스 수, `review_signal_count`=검토 대기 시그널 수, `cash_weight`=현금 비중(문자열 Decimal, 0~1). 데이터가 없으면 카운트는 `0`, `cash_weight`는 `null`.
- `cash_weight`는 **원가 기준·사용자의 첫 포트폴리오** 기준이다(MVP). 시세 연동 시 시장가 기준으로 재정의 예정.
- `*_delta` 4필드는 직전 스냅샷 대비 증감이며 **히스토리 스냅샷 도입 전까지 항상 `null`**(후속). FE는 `null`이면 증감 배지를 숨긴다.
- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

### Assets

#### `POST /api/v1/assets`

- Auth: Not required
- Request:

```json
{ "symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ" }
```

- Success `201`:

```json
{ "data": { "id": 1, "symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ", "is_active": true, "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `400 ASSET_DUPLICATE`:

```json
{ "data": null, "message": "이미 등록된 종목입니다.", "error": { "code": "ASSET_DUPLICATE" }, "meta": null }
```

#### `GET /api/v1/assets`

- Auth: Not required
- Query: `is_active?: bool`, `symbol?: string` (정확 일치 필터), `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ", "is_active": true, "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- `symbol` 지정 시 해당 심볼만 반환(0 또는 1건). `is_active`와 조합 가능. FE는 `symbol` 단일키 라우팅 보조에 사용한다(C4).
- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `GET /api/v1/assets/{asset_id}`

- Auth: Not required
- Request: path `asset_id`
- Success `200`: same `AssetResponse` envelope as asset create.
- Representative error `404 ASSET_NOT_FOUND`:

```json
{ "data": null, "message": "종목을 찾을 수 없습니다.", "error": { "code": "ASSET_NOT_FOUND" }, "meta": null }
```

#### `GET /api/v1/assets/{asset_id}/detail`

- Auth: Not required
- Request: path `asset_id`
- Success `200`:

```json
{ "data": { "id": 1, "symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ", "price": "195.64", "previous_close": "193.20", "change": "2.44", "change_percent": "1.26", "currency": "USD", "sector": "Technology", "industry": "Consumer Electronics", "description": "Makes devices and services.", "as_of": "2026-06-19T00:00:00Z", "per": "31.2", "peg": "2.1", "fifty_two_week_low": "164.08", "fifty_two_week_high": "237.49", "target_price": "210.00", "target_upside_percent": "7.34" }, "message": null, "error": null, "meta": null }
```

- 펀더멘털 6필드(`per`, `peg`, `fifty_two_week_low`, `fifty_two_week_high`, `target_price`, `target_upside_percent`)는 모두 **nullable 문자열 Decimal**이다(C5). provider가 값을 제공하지 않으면 `null`. 현재 mock provider는 AAPL에만 값을 채우고 그 외 심볼은 6필드 모두 `null`이다. FE 어댑터는 `null` 표시 fallback(예: "—")을 둔다.
- Representative error `404 ASSET_NOT_FOUND`: same as asset detail.

#### `GET /api/v1/assets/{asset_id}/research-summary`

- Auth: Required
- Request: path `asset_id`
- Success `200`:

```json
{ "data": { "asset_id": 1, "positive_factors": ["견조한 매출 성장"], "negative_factors": ["밸류에이션 부담"], "items_to_verify": ["최근 실적 발표 원문 확인"], "sources": [{ "type": "news", "label": "AAPL mock news", "url": null }], "updated_at": "2026-06-19T00:00:00Z" }, "message": null, "error": null, "meta": null }
```

- Representative error `404 ASSET_NOT_FOUND`: same as asset detail.

#### `GET /api/v1/assets/{asset_id}/buy-checklist`

- Auth: Required
- Request: path `asset_id`
- Success `200`:

```json
{ "data": { "asset_id": 1, "items": [{ "key": "valuation", "label": "밸류에이션 확인", "status": "pending", "detail": "현재 가격과 최근 실적 기준 밸류에이션을 확인하세요." }], "memo": null, "checked_item_keys": [], "is_complete": false, "decided_at": null }, "message": null, "error": null, "meta": null }
```

- Completion rule: `is_complete` is true when `memo` has non-whitespace text and all four required keys are checked.
- `decided_at`: `null` while incomplete; set when the checklist first becomes complete and preserved while it remains complete.
- Representative error `404 ASSET_NOT_FOUND`: same as asset detail.

#### `PUT /api/v1/assets/{asset_id}/buy-checklist`

- Auth: Required
- Request:

```json
{ "memo": "All checks reviewed.", "checked_item_keys": ["valuation", "news_overheated", "portfolio_concentration", "earnings_disclosure"] }
```

- Success `200`: same `BuyChecklistResponse` envelope as checklist get.
- Representative error `422 VALIDATION_ERROR`: see Auth section.

### Watchlists

#### `POST /api/v1/watchlists`

- Auth: Required
- Request:

```json
{ "name": "Core holdings" }
```

- Success `201`:

```json
{ "data": { "id": 1, "user_id": 1, "name": "Core holdings", "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `GET /api/v1/watchlists`

- Auth: Required
- Query: `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "user_id": 1, "name": "Core holdings", "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `POST /api/v1/watchlists/{watchlist_id}/items`

- Auth: Required
- Request:

```json
{ "asset_id": 1, "priority": 10, "reason": "Core AI exposure", "tags": ["ai", "large-cap"], "memo": "Watch earnings." }
```

- Success `201`:

```json
{ "data": { "id": 1, "watchlist_id": 1, "asset_id": 1, "priority": 10, "reason": "Core AI exposure", "tags": ["ai", "large-cap"], "memo": "Watch earnings.", "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `400 WATCHLIST_ITEM_DUPLICATE`:

```json
{ "data": null, "message": "이미 관심 목록에 추가된 종목입니다.", "error": { "code": "WATCHLIST_ITEM_DUPLICATE" }, "meta": null }
```

#### `GET /api/v1/watchlists/{watchlist_id}/items`

- Auth: Required
- Query: `page: int = 1`, `size: int = 20`, `sort: priority | -priority | created_at | -created_at = priority`, `expand?: string` (콤마 구분, 지원값 `asset`)
- Success `200`:

```json
{ "data": [{ "id": 1, "watchlist_id": 1, "asset_id": 1, "priority": 10, "reason": "Core AI exposure", "tags": ["ai", "large-cap"], "memo": "Watch earnings.", "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- `expand=asset` 지정 시 각 item에 `asset` 객체가 추가된다(하위호환: 미지정/타값이면 `asset` 키 없음). `asset`은 `{ symbol, name, price, change_percent, sector? }`로 `price`·`change_percent`는 문자열 Decimal(C5)이며 `get_market_provider()` 시세를 합친 값이다.

```json
{ "data": [{ "id": 1, "watchlist_id": 1, "asset_id": 1, "priority": 10, "reason": "Core AI exposure", "tags": ["ai", "large-cap"], "memo": "Watch earnings.", "created_at": "2026-06-19T00:00:00", "asset": { "symbol": "AAPL", "name": "Apple Inc.", "price": "195.64", "change_percent": "1.26", "sector": "Technology" } }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `403 WATCHLIST_FORBIDDEN`:

```json
{ "data": null, "message": "관심 목록 접근 권한이 없습니다.", "error": { "code": "WATCHLIST_FORBIDDEN" }, "meta": null }
```

#### `DELETE /api/v1/watchlists/{watchlist_id}/items/{item_id}`

- Auth: Required
- Request: path `watchlist_id`, `item_id`
- Success `200`:

```json
{ "data": null, "message": null, "error": null, "meta": null }
```

- Representative error `404 WATCHLIST_ITEM_NOT_FOUND`:

```json
{ "data": null, "message": "관심 목록 종목을 찾을 수 없습니다.", "error": { "code": "WATCHLIST_ITEM_NOT_FOUND" }, "meta": null }
```

### Portfolios

#### `POST /api/v1/portfolios`

- Auth: Required
- Request:

```json
{ "name": "Long term", "concentration_threshold": "0.4", "cash_balance": "100" }
```

- Success `201`:

```json
{ "data": { "id": 1, "user_id": 1, "name": "Long term", "concentration_threshold": "0.4", "cash_balance": "0", "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `GET /api/v1/portfolios`

- Auth: Required
- Query: `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "user_id": 1, "name": "Long term", "concentration_threshold": "0.4", "cash_balance": "0", "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `GET /api/v1/portfolios/{portfolio_id}/summary`

- Auth: Required
- Request: path `portfolio_id`
- Success `200`:

```json
{ "data": { "portfolio_id": 1, "concentration_threshold": "0.4", "total_cost_value": "1000", "total_value": "2056.4", "cash_balance": "100", "cash_weight": "0.048628671465", "has_sector_concentration": true, "positions": [{ "asset_id": 1, "quantity": "10", "avg_buy_price": "100", "cost_value": "1000", "market_value": "1956.4", "cost_weight": "1", "weight": "0.951371328535", "exceeds_threshold": true }], "sector_weights": [{ "sector": "Technology", "market_value": "1956.4", "weight": "0.951371328535", "exceeds_threshold": true }] }, "message": null, "error": null, "meta": null }
```

- `total_value` is market value plus `cash_balance`.
- `positions[].weight`, `sector_weights[].weight`, and `cash_weight` are based on `total_value`.
- `positions[].cost_weight` remains cost-basis for UIs that need the previous ratio.
- Null asset sectors are grouped under `UNKNOWN`.
- Sector concentration reuses `concentration_threshold`.

- Representative error `404 PORTFOLIO_NOT_FOUND`:

```json
{ "data": null, "message": "포트폴리오를 찾을 수 없습니다.", "error": { "code": "PORTFOLIO_NOT_FOUND" }, "meta": null }
```

#### `POST /api/v1/portfolios/{portfolio_id}/check`

- Auth: Required
- Request: path `portfolio_id`
- Success `200`:

```json
{ "data": { "summary": { "portfolio_id": 1, "concentration_threshold": "0.4", "total_cost_value": "1000", "total_value": "2056.4", "cash_balance": "100", "cash_weight": "0.048628671465", "has_sector_concentration": true, "positions": [], "sector_weights": [] }, "created_signals": [] }, "message": null, "error": null, "meta": null }
```

- Representative error `403 PORTFOLIO_FORBIDDEN`:

```json
{ "data": null, "message": "포트폴리오 접근 권한이 없습니다.", "error": { "code": "PORTFOLIO_FORBIDDEN" }, "meta": null }
```

#### `POST /api/v1/portfolios/{portfolio_id}/positions`

- Auth: Required
- Request:

```json
{ "asset_id": 1, "quantity": "10", "avg_buy_price": "100" }
```

- Success `201`:

```json
{ "data": { "id": 1, "portfolio_id": 1, "asset_id": 1, "quantity": "10", "avg_buy_price": "100", "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `400 POSITION_DUPLICATE`:

```json
{ "data": null, "message": "이미 포트폴리오에 추가된 종목입니다.", "error": { "code": "POSITION_DUPLICATE" }, "meta": null }
```

#### `PATCH /api/v1/portfolios/{portfolio_id}/positions/{position_id}`

- Auth: Required
- Request:

```json
{ "quantity": "12", "avg_buy_price": "95" }
```

- Success `200`: same `PositionResponse` envelope as position create.
- Representative error `404 POSITION_NOT_FOUND`:

```json
{ "data": null, "message": "보유 종목을 찾을 수 없습니다.", "error": { "code": "POSITION_NOT_FOUND" }, "meta": null }
```

#### `DELETE /api/v1/portfolios/{portfolio_id}/positions/{position_id}`

- Auth: Required
- Request: path `portfolio_id`, `position_id`
- Success `200`:

```json
{ "data": null, "message": null, "error": null, "meta": null }
```

- Representative error `404 POSITION_NOT_FOUND`: same as position update.

### Theses

#### `POST /api/v1/theses`

- Auth: Required
- Request:

```json
{ "asset_id": 1, "summary": "Revenue growth thesis", "risk_factors": "FX risk", "invalidation_conditions": "Growth below 5%" }
```

- Success `201`:

```json
{ "data": { "id": 1, "user_id": 1, "asset_id": 1, "summary": "Revenue growth thesis", "risk_factors": "FX risk", "invalidation_conditions": "Growth below 5%", "is_active": true, "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `404 ASSET_NOT_FOUND`: see Assets section.

#### `PUT /api/v1/theses/{thesis_id}`

- Auth: Required
- Request:

```json
{ "summary": "Updated thesis", "risk_factors": null, "invalidation_conditions": "Margin compression" }
```

- Success `200`: same `ThesisResponse` envelope as thesis create.
- Representative error `403 THESIS_FORBIDDEN`:

```json
{ "data": null, "message": "투자 가설 접근 권한이 없습니다.", "error": { "code": "THESIS_FORBIDDEN" }, "meta": null }
```

#### `GET /api/v1/theses/latest?asset_id={asset_id}`

- Auth: Required
- Request: query `asset_id`
- Success `200`: same `ThesisResponse` envelope as thesis create.
- Representative error `404 THESIS_NOT_FOUND`:

```json
{ "data": null, "message": "투자 가설을 찾을 수 없습니다.", "error": { "code": "THESIS_NOT_FOUND" }, "meta": null }
```

#### `PATCH /api/v1/theses/{thesis_id}/deactivate`

- Auth: Required
- Request: path `thesis_id`
- Success `200`: same `ThesisResponse` envelope as thesis create with `is_active: false`.
- Representative error `404 THESIS_NOT_FOUND`: same as latest thesis.

### Reports

#### `POST /api/v1/reports`

- Auth: Required
- Request:

```json
{ "asset_id": 1, "thesis_id": 1, "summary": "AI demand remains strong", "positive_factors": ["Revenue beat"], "negative_factors": ["Valuation"], "risk_level": "MEDIUM", "thesis_conflict_status": "NONE", "conflict_reason": null, "news_item_ids": [10] }
```

- Success `201`:

```json
{ "data": { "id": 1, "asset_id": 1, "thesis_id": 1, "summary": "AI demand remains strong", "positive_factors": ["Revenue beat"], "negative_factors": ["Valuation"], "risk_level": "MEDIUM", "thesis_conflict_status": "NONE", "conflict_reason": null, "news_item_ids": [10], "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `GET /api/v1/reports?asset_id={asset_id}`

- Auth: Required
- Query: `asset_id: int`, `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "asset_id": 1, "thesis_id": 1, "summary": "AI demand remains strong", "positive_factors": ["Revenue beat"], "negative_factors": ["Valuation"], "risk_level": "MEDIUM", "thesis_conflict_status": "NONE", "conflict_reason": null, "news_item_ids": [10], "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `GET /api/v1/reports/{report_id}`

- Auth: Required
- Request: path `report_id`
- Success `200`: same `ResearchReportResponse` envelope as report create.
- Representative error `404 REPORT_NOT_FOUND`:

```json
{ "data": null, "message": "리포트를 찾을 수 없습니다.", "error": { "code": "REPORT_NOT_FOUND" }, "meta": null }
```

### Signals

#### `POST /api/v1/signals`

- Auth: Required
- Request:

```json
{ "asset_id": 1, "thesis_id": 1, "news_item_id": 10, "signal_type": "RISK_ALERT", "score": 80, "risk_level": "HIGH", "reason": "Thesis conflict detected", "evidence": { "report_id": 1 }, "expires_at": "2026-06-26T00:00:00" }
```

- Success `201`:

```json
{ "data": { "id": 1, "asset_id": 1, "thesis_id": 1, "news_item_id": 10, "signal_type": "RISK_ALERT", "score": 80, "risk_level": "HIGH", "reason": "Thesis conflict detected", "evidence": { "report_id": 1 }, "expires_at": "2026-06-26T00:00:00", "is_expired": false, "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `GET /api/v1/signals?asset_id={asset_id}`

- Auth: Required
- Query: `asset_id: int`, `include_expired: bool = false`, `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "asset_id": 1, "thesis_id": 1, "news_item_id": 10, "signal_type": "RISK_ALERT", "score": 80, "risk_level": "HIGH", "reason": "Thesis conflict detected", "evidence": { "report_id": 1 }, "expires_at": "2026-06-26T00:00:00", "is_expired": false, "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `GET /api/v1/signals/{signal_id}`

- Auth: Required
- Request: path `signal_id`
- Success `200`: same `SignalResponse` envelope as signal create.
- Representative error `404 SIGNAL_NOT_FOUND`:

```json
{ "data": null, "message": "신호를 찾을 수 없습니다.", "error": { "code": "SIGNAL_NOT_FOUND" }, "meta": null }
```

### Alerts

#### `GET /api/v1/alerts`

- Auth: Required
- Query: `status?: UNREAD | READ | DISMISSED`, `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "user_id": 1, "signal_id": 1, "status": "UNREAD", "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `POST /api/v1/alerts/{alert_id}/read`

- Auth: Required
- Request: path `alert_id`
- Success `200`:

```json
{ "data": { "id": 1, "user_id": 1, "signal_id": 1, "status": "READ", "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `404 ALERT_NOT_FOUND`:

```json
{ "data": null, "message": "알림을 찾을 수 없습니다.", "error": { "code": "ALERT_NOT_FOUND" }, "meta": null }
```

#### `POST /api/v1/alerts/{alert_id}/dismiss`

- Auth: Required
- Request: path `alert_id`
- Success `200`:

```json
{ "data": { "id": 1, "user_id": 1, "signal_id": 1, "status": "DISMISSED", "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `404 ALERT_NOT_FOUND`: same as mark read.

### Alert Candidates

#### `GET /api/v1/alert-candidates`

- Auth: Required
- Query: `candidate_type?: NEWS_SURGE | PRICE_MOVEMENT | DISCLOSURE | PORTFOLIO_CONCENTRATION | BUY_CHECKLIST_REQUIRED`, `importance?: LOW | MEDIUM | HIGH`, `status?: UNREAD | READ | CONFIRMED`, `page: int = 1`, `size: int = 20`, `sort: created_at | -created_at | id | -id = -created_at`
- Success `200`:

```json
{ "data": [{ "id": 1, "user_id": 1, "candidate_type": "NEWS_SURGE", "importance": "HIGH", "status": "UNREAD", "title": "News volume increased", "message": "Review before sending a notification.", "asset_id": 1, "evidence": { "source": "mock" }, "created_at": "2026-06-20T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `POST /api/v1/alert-candidates/{candidate_id}/read`

- Auth: Required
- Request: path `candidate_id`
- Success `200`:

```json
{ "data": { "id": 1, "user_id": 1, "candidate_type": "NEWS_SURGE", "importance": "HIGH", "status": "READ", "title": "News volume increased", "message": "Review before sending a notification.", "asset_id": 1, "evidence": { "source": "mock" }, "created_at": "2026-06-20T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `404 ALERT_CANDIDATE_NOT_FOUND`:

```json
{ "data": null, "message": "알림 후보를 찾을 수 없습니다.", "error": { "code": "ALERT_CANDIDATE_NOT_FOUND" }, "meta": null }
```

#### `POST /api/v1/alert-candidates/{candidate_id}/confirm`

- Auth: Required
- Request: path `candidate_id`
- Success `200`:

```json
{ "data": { "id": 1, "user_id": 1, "candidate_type": "NEWS_SURGE", "importance": "HIGH", "status": "CONFIRMED", "title": "News volume increased", "message": "Review before sending a notification.", "asset_id": 1, "evidence": { "source": "mock" }, "created_at": "2026-06-20T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `404 ALERT_CANDIDATE_NOT_FOUND`: same as mark read.

### Job Runs and Worker

#### `GET /api/v1/job-runs`

- Auth: Not required
- Query: `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "job_type": "news", "status": "queued", "started_at": null, "finished_at": null, "error_message": null, "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `POST /api/v1/worker/jobs/news`

- Auth: Not required
- Request:

```json
{ "symbols": ["AAPL", "MSFT"] }
```

- Success `200`:

```json
{ "data": { "job_id": "rq-job-id", "status": "queued" }, "message": null, "error": null, "meta": null }
```

- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `POST /api/v1/worker/jobs/analysis`

- Auth: Not required
- Request:

```json
{ "watchlist_id": 1 }
```

- Success `200`:

```json
{ "data": { "job_id": "rq-job-id", "status": "queued" }, "message": null, "error": null, "meta": null }
```

- Representative error `404 WATCHLIST_NOT_FOUND`:

```json
{ "data": null, "message": "관심 목록을 찾을 수 없습니다.", "error": { "code": "WATCHLIST_NOT_FOUND" }, "meta": null }
```

#### `POST /api/v1/worker/scheduler/jobs/{job_name}/run`

- Auth: Not required
- Request: path `job_name` (현재 등록된 job: `mock_collection`)
- Success `200`:

```json
{ "data": { "job_name": "mock_collection", "job_run_id": 1, "status": "success" }, "message": null, "error": null, "meta": null }
```

- Notes: 등록된 scheduler job을 실제 주기 트리거 등록 없이 한 번 즉시 실행한다. Redis 없이 동작한다.
- Representative error `404`: unknown job name. `409`: disabled job.

### Health

#### `GET /health`

- Auth: Not required
- Request: none
- Success `200`:

```json
{ "status": "ok" }
```

- Notes: root health endpoint for infrastructure/monitoring compatibility. It intentionally mirrors `/api/v1/health` and does not use the common envelope.
- Representative error: unhandled server errors use `500 INTERNAL_ERROR` envelope.

#### `GET /api/v1/health`

- Auth: Not required
- Request: none
- Success `200`:

```json
{ "status": "ok" }
```

- Notes: versioned health endpoint for API clients/Swagger discovery. It intentionally mirrors `/health` and does not use the common envelope.
- Representative error: unhandled server errors use `500 INTERNAL_ERROR` envelope.

#### `GET /api/v1/health/readiness`

- Auth: Not required
- Request: none
- Success `200`:

```json
{ "status": "ok", "checks": { "db": { "status": "ok" } }, "providers": { "market": "mock", "news": "mock", "disclosure": "mock", "portfolio": "mock" }, "version": "0.1.0" }
```

- Notes: dependency readiness, provider modes, application version. Does not use the common envelope.
- Dependency failure `503`: same shape with `status: "error"` and the failing entry in `checks` set to `{ "status": "error" }` (현재 `db` 점검만 수행한다).

## Candidate APIs Not Implemented

아래 항목은 현재 구현되어 있지 않다. 프론트 화면에서 필요하면 후속 이슈에서 API 계약을 확정한다.

| Screen | Candidate |
| --- | --- |
| 관심종목 | 관심목록 상세와 포함 항목 목록을 한 번에 반환하는 API (현재는 items에 `expand=asset`로 시세만 합침) |
| 설정 | 알림 설정 조회/수정 API |

## Route Checklist

- [x] `POST /api/v1/auth/register`
- [x] `POST /api/v1/auth/login`
- [x] `GET /api/v1/auth/me`
- [x] `POST /api/v1/assets`
- [x] `GET /api/v1/assets`
- [x] `GET /api/v1/assets/{asset_id}`
- [x] `POST /api/v1/watchlists`
- [x] `GET /api/v1/watchlists`
- [x] `POST /api/v1/watchlists/{watchlist_id}/items`
- [x] `DELETE /api/v1/watchlists/{watchlist_id}/items/{item_id}`
- [x] `POST /api/v1/portfolios`
- [x] `GET /api/v1/portfolios`
- [x] `GET /api/v1/portfolios/{portfolio_id}/summary`
- [x] `POST /api/v1/portfolios/{portfolio_id}/check`
- [x] `POST /api/v1/portfolios/{portfolio_id}/positions`
- [x] `PATCH /api/v1/portfolios/{portfolio_id}/positions/{position_id}`
- [x] `DELETE /api/v1/portfolios/{portfolio_id}/positions/{position_id}`
- [x] `POST /api/v1/theses`
- [x] `PUT /api/v1/theses/{thesis_id}`
- [x] `GET /api/v1/theses/latest`
- [x] `PATCH /api/v1/theses/{thesis_id}/deactivate`
- [x] `POST /api/v1/reports`
- [x] `GET /api/v1/reports`
- [x] `GET /api/v1/reports/{report_id}`
- [x] `POST /api/v1/signals`
- [x] `GET /api/v1/signals`
- [x] `GET /api/v1/signals/{signal_id}`
- [x] `GET /api/v1/alert-candidates`
- [x] `POST /api/v1/alert-candidates/{candidate_id}/read`
- [x] `POST /api/v1/alert-candidates/{candidate_id}/confirm`
- [x] `GET /api/v1/alerts`
- [x] `POST /api/v1/alerts/{alert_id}/read`
- [x] `POST /api/v1/alerts/{alert_id}/dismiss`
- [x] `GET /api/v1/job-runs`
- [x] `POST /api/v1/worker/jobs/news`
- [x] `POST /api/v1/worker/jobs/analysis`
- [x] `POST /api/v1/worker/scheduler/jobs/{job_name}/run`
- [x] `GET /health`
- [x] `GET /api/v1/health`
- [x] `GET /api/v1/health/readiness`
- [x] `GET /api/v1/dashboard/summary`
