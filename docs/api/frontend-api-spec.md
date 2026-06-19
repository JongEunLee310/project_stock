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

목록 응답은 `meta`에 `{ "page": 1, "size": 20, "total": 1 }`을 포함한다. 실패 응답은 `data: null`, `meta: null`이며 `error.code`에는 `ErrorCode` 문자열이 들어간다. `/health`와 `/api/v1/health`는 모니터링 호환을 위해 envelope를 사용하지 않는다.

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

## Screen Map

### 대시보드

| Purpose | Method | Path | Auth | Notes |
| --- | --- | --- | --- | --- |
| 알림 후보/시그널 요약 | `GET` | `/api/v1/signals?asset_id={asset_id}&include_expired=false&page=1&size=20` | Required | 현재 asset 단위 조회. 전체 대시보드 집계 API는 미구현 후보. |
| 포트폴리오 목록 | `GET` | `/api/v1/portfolios?page=1&size=20` | Required | 요약 조회 전 선택 목록. |
| 포트폴리오 요약 | `GET` | `/api/v1/portfolios/{portfolio_id}/summary` | Required | 집중도/비중 표시. |
| 관심종목 목록 | `GET` | `/api/v1/watchlists?page=1&size=20` | Required | 사용자 관심종목 그룹 목록. |
| 알림 목록 | `GET` | `/api/v1/alerts?status=UNREAD&page=1&size=20` | Required | unread 카드/배지 표시. |

### 관심종목

| Purpose | Method | Path | Auth |
| --- | --- | --- | --- |
| 목록 조회 | `GET` | `/api/v1/watchlists?page=1&size=20` | Required |
| 관심목록 생성 | `POST` | `/api/v1/watchlists` | Required |
| 관심종목 추가 | `POST` | `/api/v1/watchlists/{watchlist_id}/items` | Required |
| 관심종목 제거 | `DELETE` | `/api/v1/watchlists/{watchlist_id}/items/{item_id}` | Required |

### 종목상세

| Purpose | Method | Path | Auth |
| --- | --- | --- | --- |
| 종목 정보 | `GET` | `/api/v1/assets/{asset_id}` | Not required |
| 최신 투자 가설 | `GET` | `/api/v1/theses/latest?asset_id={asset_id}` | Required |
| 리서치 리포트 목록 | `GET` | `/api/v1/reports?asset_id={asset_id}&page=1&size=20` | Required |
| 시그널 목록 | `GET` | `/api/v1/signals?asset_id={asset_id}&include_expired=false&page=1&size=20` | Required |

### 리서치요약

| Purpose | Method | Path | Auth | Notes |
| --- | --- | --- | --- | --- |
| 리포트 목록 | `GET` | `/api/v1/reports?asset_id={asset_id}&page=1&size=20` | Required | thesis conflict 필드는 report payload에 포함. |
| 리포트 상세 | `GET` | `/api/v1/reports/{report_id}` | Required | 요약/근거/위험 수준 표시. |
| 리포트 생성 | `POST` | `/api/v1/reports` | Required | 운영/관리성 생성 API. |
| 가설 생성/수정/비활성화 | `POST/PUT/PATCH` | `/api/v1/theses...` | Required | 화면 편집 기능이 필요할 때 사용. |

### 알림후보

| Purpose | Method | Path | Auth |
| --- | --- | --- | --- |
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
- Query: `is_active?: bool`, `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ", "is_active": true, "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `GET /api/v1/assets/{asset_id}`

- Auth: Not required
- Request: path `asset_id`
- Success `200`: same `AssetResponse` envelope as asset create.
- Representative error `404 ASSET_NOT_FOUND`:

```json
{ "data": null, "message": "종목을 찾을 수 없습니다.", "error": { "code": "ASSET_NOT_FOUND" }, "meta": null }
```

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
{ "asset_id": 1, "priority": 10 }
```

- Success `201`:

```json
{ "data": { "id": 1, "watchlist_id": 1, "asset_id": 1, "priority": 10, "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `400 WATCHLIST_ITEM_DUPLICATE`:

```json
{ "data": null, "message": "이미 관심 목록에 추가된 종목입니다.", "error": { "code": "WATCHLIST_ITEM_DUPLICATE" }, "meta": null }
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
{ "name": "Long term", "concentration_threshold": "0.4" }
```

- Success `201`:

```json
{ "data": { "id": 1, "user_id": 1, "name": "Long term", "concentration_threshold": "0.4", "created_at": "2026-06-19T00:00:00" }, "message": null, "error": null, "meta": null }
```

- Representative error `422 VALIDATION_ERROR`: see Auth section.

#### `GET /api/v1/portfolios`

- Auth: Required
- Query: `page: int = 1`, `size: int = 20`
- Success `200`:

```json
{ "data": [{ "id": 1, "user_id": 1, "name": "Long term", "concentration_threshold": "0.4", "created_at": "2026-06-19T00:00:00" }], "message": null, "error": null, "meta": { "page": 1, "size": 20, "total": 1 } }
```

- Representative error `401 AUTH_INVALID_TOKEN`: see Auth section.

#### `GET /api/v1/portfolios/{portfolio_id}/summary`

- Auth: Required
- Request: path `portfolio_id`
- Success `200`:

```json
{ "data": { "portfolio_id": 1, "concentration_threshold": "0.4", "total_cost_value": "1000", "positions": [{ "asset_id": 1, "quantity": "10", "avg_buy_price": "100", "cost_value": "1000", "weight": "1", "exceeds_threshold": true }] }, "message": null, "error": null, "meta": null }
```

- Representative error `404 PORTFOLIO_NOT_FOUND`:

```json
{ "data": null, "message": "포트폴리오를 찾을 수 없습니다.", "error": { "code": "PORTFOLIO_NOT_FOUND" }, "meta": null }
```

#### `POST /api/v1/portfolios/{portfolio_id}/check`

- Auth: Required
- Request: path `portfolio_id`
- Success `200`:

```json
{ "data": { "summary": { "portfolio_id": 1, "concentration_threshold": "0.4", "total_cost_value": "1000", "positions": [] }, "created_signals": [] }, "message": null, "error": null, "meta": null }
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

## Candidate APIs Not Implemented

아래 항목은 현재 구현되어 있지 않다. 프론트 화면에서 필요하면 후속 이슈에서 API 계약을 확정한다.

| Screen | Candidate |
| --- | --- |
| 대시보드 | 전체 자산/전체 포트폴리오를 합산한 대시보드 집계 API |
| 관심종목 | 관심목록 상세과 포함 항목 목록을 한 번에 반환하는 API |
| 알림후보 | 시그널에서 알림 후보를 생성/승인하는 전용 API |
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
- [x] `GET /api/v1/alerts`
- [x] `POST /api/v1/alerts/{alert_id}/read`
- [x] `POST /api/v1/alerts/{alert_id}/dismiss`
- [x] `GET /api/v1/job-runs`
- [x] `POST /api/v1/worker/jobs/news`
- [x] `POST /api/v1/worker/jobs/analysis`
- [x] `GET /health`
- [x] `GET /api/v1/health`
