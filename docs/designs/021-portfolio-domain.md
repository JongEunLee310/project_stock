# Design: Portfolio 도메인 (Issue #21)

자동 증권사 연동 전 단계로, 사용자가 보유 종목을 수동 입력·관리하는 기본 구조를 정의한다.

## 테이블: portfolios

| 필드 | 타입 | 제약 |
|------|------|------|
| id | Integer | PK |
| user_id | Integer | FK(users.id), NOT NULL |
| name | String(255) | NOT NULL |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

## 테이블: positions

| 필드 | 타입 | 제약 |
|------|------|------|
| id | Integer | PK |
| portfolio_id | Integer | FK(portfolios.id), NOT NULL |
| asset_id | Integer | FK(assets.id), NOT NULL |
| quantity | Numeric(20, 8) | NOT NULL |
| avg_buy_price | Numeric(20, 4) | NOT NULL |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

유니크 제약: `unique(portfolio_id, asset_id)`

## 스키마

- `PortfolioCreate`: name
- `PortfolioResponse`: id, user_id, name, created_at (from_attributes=True)
- `PositionCreate`: asset_id, quantity, avg_buy_price
- `PositionUpdate`: quantity, avg_buy_price (둘 다 선택, 최소 1개 필요)
- `PositionResponse`: id, portfolio_id, asset_id, quantity, avg_buy_price, created_at (from_attributes=True)

## Repository

- `PortfolioRepository`
  - `get_by_id(id) -> Portfolio | None`
  - `list_by_user(user_id) -> list[Portfolio]`
  - `create(user_id, name) -> Portfolio`
- `PositionRepository`
  - `get_by_id(id) -> Position | None`
  - `list_by_portfolio(portfolio_id) -> list[Position]`
  - `create(portfolio_id, data) -> Position`
  - `update(position, data) -> Position`
  - `delete(position_id) -> None`

## Service

- `PortfolioService`
  - `create_portfolio(user_id, data) -> PortfolioResponse`
  - `list_portfolios(user_id) -> list[PortfolioResponse]`
  - `add_position(portfolio_id, user_id, data) -> PositionResponse` — 소유권 검증, 동일 종목 중복 거부
  - `update_position(portfolio_id, position_id, user_id, data) -> PositionResponse` — 소유권 검증
  - `remove_position(portfolio_id, position_id, user_id) -> None` — 소유권 검증

## API (인증 필요)

| Method | Path | 요청 | 응답 |
|--------|------|------|------|
| POST | /api/v1/portfolios | PortfolioCreate | PortfolioResponse 201 |
| GET | /api/v1/portfolios | — | list[PortfolioResponse] |
| POST | /api/v1/portfolios/{id}/positions | PositionCreate | PositionResponse 201 |
| PATCH | /api/v1/portfolios/{id}/positions/{position_id} | PositionUpdate | PositionResponse |
| DELETE | /api/v1/portfolios/{id}/positions/{position_id} | — | 204 |

소유권: 다른 사용자의 portfolio 접근 시 403. 동일 종목 중복 추가 시 400.

## 의존성

- Issue #5 (Asset 도메인) — positions.asset_id FK
- users 도메인 — portfolios.user_id FK, `get_current_user`

## 가격/평가 정책

- 본 도메인은 보유 수량과 평균 매수가만 저장한다. 현재가/시세 소스는 도입하지 않는다.
- 비중 계산은 Issue #22에서 **매수원가 기준**(quantity × avg_buy_price)으로 수행한다.
  현재가 평가금액은 MVP 범위 밖(자동매매 제외 범위와 일관).

## Alembic 마이그레이션

신규 파일: `alembic/versions/<rev>_create_portfolios_tables.py`
`down_revision`은 현재 head revision `9c0d1e23f405`(create_alerts)를 참조.
