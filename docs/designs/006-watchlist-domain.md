# Design: Watchlist 도메인 (Issue #6)

## 테이블: watchlists

| 필드 | 타입 | 제약 |
|------|------|------|
| id | Integer | PK |
| user_id | Integer | FK(users.id), NOT NULL |
| name | String(255) | NOT NULL |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

## 테이블: watchlist_items

| 필드 | 타입 | 제약 |
|------|------|------|
| id | Integer | PK |
| watchlist_id | Integer | FK(watchlists.id), NOT NULL |
| asset_id | Integer | FK(assets.id), NOT NULL |
| priority | Integer | NOT NULL, default=0 |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

유니크 제약: `unique(watchlist_id, asset_id)`

## 스키마

- `WatchlistCreate`: name
- `WatchlistResponse`: id, user_id, name, created_at (from_attributes=True)
- `WatchlistItemCreate`: asset_id, priority
- `WatchlistItemResponse`: id, watchlist_id, asset_id, priority, created_at (from_attributes=True)

## Repository

- `WatchlistRepository`
  - `get_by_id(id) -> Watchlist | None`
  - `list_by_user(user_id) -> list[Watchlist]`
  - `create(user_id, name) -> Watchlist`
- `WatchlistItemRepository`
  - `get_by_id(id) -> WatchlistItem | None`
  - `list_by_watchlist(watchlist_id) -> list[WatchlistItem]`
  - `create(watchlist_id, asset_id, priority) -> WatchlistItem`
  - `delete(item_id) -> None`

## Service

- `create_watchlist(user_id, data) -> WatchlistResponse`
- `list_watchlists(user_id) -> list[WatchlistResponse]`
- `add_item(watchlist_id, user_id, data) -> WatchlistItemResponse` — 소유권 검증, 중복 거부
- `remove_item(watchlist_id, item_id, user_id) -> None` — 소유권 검증

## API (인증 필요)

| Method | Path | 요청 | 응답 |
|--------|------|------|------|
| POST | /api/v1/watchlists | WatchlistCreate | WatchlistResponse 201 |
| GET | /api/v1/watchlists | — | list[WatchlistResponse] |
| POST | /api/v1/watchlists/{id}/items | WatchlistItemCreate | WatchlistItemResponse 201 |
| DELETE | /api/v1/watchlists/{id}/items/{item_id} | — | 204 |

## 의존성

- Issue #5 (Asset 도메인) — watchlist_items.asset_id FK

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_create_watchlists_tables.py`  
`down_revision`은 assets 마이그레이션 revision ID를 참조.
