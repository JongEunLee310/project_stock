# Design: News Item 도메인 (Issue #9)

## 테이블: news_items

| 필드 | 타입 | 제약 |
|---|---|---|
| id | Integer | PK |
| raw_news_event_id | Integer | FK(raw_news_events.id), nullable |
| asset_id | Integer | FK(assets.id), NOT NULL |
| title | String(500) | NOT NULL |
| url | String(2048) | NOT NULL |
| source | String(100) | NOT NULL |
| published_at | DateTime(tz) | nullable |
| summary | Text | nullable |
| sentiment | String(20) | nullable (positive/negative/neutral) |
| impact_level | String(20) | nullable (high/medium/low) |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

인덱스: `ix_news_items_asset_id (asset_id)`

## 스키마

- `NewsItemCreate`: raw_news_event_id, asset_id, title, url, source, published_at, summary, sentiment, impact_level
- `NewsItemResponse`: id, raw_news_event_id, asset_id, title, url, source, published_at, summary, sentiment, impact_level, created_at

## Repository

- `create(data: NewsItemCreate) -> NewsItem`
- `list_by_asset(asset_id: int) -> list[NewsItem]`

## 의존성

- Issue #8 (RawNewsEvent) — news_items.raw_news_event_id FK
- Issue #5 (Asset 도메인) — news_items.asset_id FK

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_create_news_items_table.py`  
`down_revision`: raw_news_events 마이그레이션 revision ID
