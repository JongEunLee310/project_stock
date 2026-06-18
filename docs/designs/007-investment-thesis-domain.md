# Design: Investment Thesis 도메인 (Issue #7)

## 테이블: investment_theses

| 필드 | 타입 | 제약 |
|------|------|------|
| id | Integer | PK |
| user_id | Integer | FK(users.id), NOT NULL |
| asset_id | Integer | FK(assets.id), NOT NULL |
| summary | Text | NOT NULL |
| risk_factors | Text | nullable |
| invalidation_conditions | Text | nullable |
| is_active | Boolean | NOT NULL, default=True |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

인덱스: `ix_investment_theses_asset_id (asset_id)`

## 스키마

- `ThesisCreate`: asset_id, summary, risk_factors, invalidation_conditions
- `ThesisUpdate`: summary, risk_factors, invalidation_conditions (모두 optional)
- `ThesisResponse`: id, user_id, asset_id, summary, risk_factors, invalidation_conditions, is_active, created_at (from_attributes=True)

## Repository

- `get_by_id(id) -> InvestmentThesis | None`
- `get_latest_by_asset(asset_id, user_id) -> InvestmentThesis | None`
- `list_by_asset(asset_id, user_id) -> list[InvestmentThesis]`
- `create(user_id, asset_id, ...) -> InvestmentThesis`
- `update(thesis_id, ...) -> InvestmentThesis`
- `deactivate(thesis_id) -> InvestmentThesis`

## Service

- `create(user_id, data) -> ThesisResponse` — asset 존재 검증
- `update(thesis_id, user_id, data) -> ThesisResponse` — 소유권 검증
- `get_latest(asset_id, user_id) -> ThesisResponse`
- `deactivate(thesis_id, user_id) -> ThesisResponse` — 소유권 검증

## API (인증 필요)

| Method | Path | 요청 | 응답 |
|--------|------|------|------|
| POST | /api/v1/theses | ThesisCreate | ThesisResponse 201 |
| PUT | /api/v1/theses/{id} | ThesisUpdate | ThesisResponse |
| GET | /api/v1/theses/latest | ?asset_id=int | ThesisResponse |
| PATCH | /api/v1/theses/{id}/deactivate | — | ThesisResponse |

## 의존성

- Issue #5 (Asset 도메인) — investment_theses.asset_id FK

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_create_investment_theses_table.py`  
`down_revision`은 assets 마이그레이션 revision ID를 참조.
