# Design: Raw News 저장 구조 (Issue #8)

## 테이블: raw_news_events

| 필드 | 타입 | 제약 |
|---|---|---|
| id | Integer | PK |
| title | String(500) | NOT NULL |
| url | String(2048) | NOT NULL, UNIQUE |
| body | Text | nullable |
| source | String(100) | NOT NULL |
| published_at | DateTime(tz) | nullable |
| collected_at | DateTime(tz) | NOT NULL, server_default=now() |
| payload | JSON | nullable |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

제약: `uq_raw_news_events_url (url)`

## 스키마

- `RawNewsEventCreate`: title, url, body, source, published_at, collected_at, payload
- `RawNewsEventResponse`: id, title, url, source, published_at, collected_at, created_at

## Repository

- `create_or_skip(data: RawNewsEventCreate) -> RawNewsEvent | None` — URL 중복 시 None 반환
- `get_by_url(url: str) -> RawNewsEvent | None`

## 의존성

없음 (최상위 도메인)

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_create_raw_news_events_table.py`  
`down_revision`: `8c3f0d2b7a91`
