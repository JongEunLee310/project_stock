# 030 Watchlist API Improvement

## Scope

프론트엔드 관심종목 화면에서 watchlist item의 사유, 태그, 메모를 표시하고 정렬된 item 목록을 조회할 수 있게 한다.

## Data Model

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `reason` | `Text` | No | 관심 사유 |
| `tags` | `JSON list[str]` | No | 기본값 `[]`, 별도 태그 테이블 없음 |
| `memo` | `Text` | No | 사용자 메모 |

기존 `uq_watchlist_items_asset(watchlist_id, asset_id)` 제약은 유지한다.

## API

`POST /api/v1/watchlists/{watchlist_id}/items`

- Request: `asset_id`, `priority`, `reason?`, `tags?`, `memo?`
- Response: `WatchlistItemResponse`
- Duplicate: `400 WATCHLIST_ITEM_DUPLICATE`

`GET /api/v1/watchlists/{watchlist_id}/items`

- Auth: Required
- Query: `page=1`, `size=20`, `sort=priority`
- Sort values: `priority`, `-priority`, `created_at`, `-created_at`
- Response: paginated `WatchlistItemResponse[]`

## Decisions

- `tags` is stored as a JSON list for round-trip fidelity without a new tag domain.
- Ownership checks reuse `WATCHLIST_NOT_FOUND` and `WATCHLIST_FORBIDDEN`.
