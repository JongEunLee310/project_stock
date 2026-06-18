# Design: Asset 도메인 (Issue #5)

## 테이블: assets

| 필드 | 타입 | 제약 |
|------|------|------|
| id | Integer | PK |
| symbol | String(20) | NOT NULL |
| name | String(255) | NOT NULL |
| market | String(20) | NOT NULL |
| is_active | Boolean | NOT NULL, default=True |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

유니크 제약: `unique(symbol, market)`

## 스키마

- `AssetCreate`: symbol, name, market
- `AssetResponse`: id, symbol, name, market, is_active, created_at (from_attributes=True)

## Repository

- `get_by_id(id) -> Asset | None`
- `get_by_symbol_market(symbol, market) -> Asset | None`
- `list_all(is_active) -> list[Asset]`
- `create(symbol, name, market) -> Asset`

## Service

- `register(data: AssetCreate) -> AssetResponse` — 중복 symbol+market 거부
- `get(id) -> AssetResponse`
- `list(is_active) -> list[AssetResponse]`

## API

| Method | Path | 요청 | 응답 |
|--------|------|------|------|
| POST | /api/v1/assets | AssetCreate | AssetResponse 201 |
| GET | /api/v1/assets | ?is_active=bool | list[AssetResponse] |
| GET | /api/v1/assets/{id} | — | AssetResponse |

## 의존성

없음 (독립 도메인). Watchlist, InvestmentThesis의 전제 조건.

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_create_assets_table.py`
