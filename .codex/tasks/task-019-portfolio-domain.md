# Codex Handoff Task

## Source Issue

Issue #21: 포트폴리오 수동 입력 기본 구조 구현

## Task Summary

Portfolio(포트폴리오) 도메인을 구현한다. 사용자가 보유 종목을 수동 입력·관리하는 portfolios/positions 테이블, CRUD API, Alembic 마이그레이션을 포함한다.

## Goal

- 사용자가 포트폴리오를 생성할 수 있다.
- 사용자가 보유 종목(수량, 평균 매수가)을 수동으로 등록할 수 있다.
- 보유 종목의 수량과 평균 매수가를 수정할 수 있다.
- 보유 종목을 삭제할 수 있다.
- 사용자별 포트폴리오가 분리된다.

## Background

- 자동 증권사 연동 전 단계의 수동 입력 구조. 현재가/시세 소스는 도입하지 않는다.
- 인증된 사용자만 접근 가능 — `app/api/v1/deps.py`의 `get_current_user` 사용.
- 사용자 소유권 검증 필수: 다른 사용자의 portfolio 접근 불가.
- 기존 Watchlist 도메인(`app/domains/watchlists/`)과 동일한 레이어 구조·패턴을 따른다.
- 설계 문서: `docs/designs/021-portfolio-domain.md`
- 비중 계산(매수원가 기준)은 후속 Issue #22 범위이며 본 태스크에 포함하지 않는다.

## Implementation Scope

- `app/domains/portfolios/__init__.py`
- `app/domains/portfolios/model.py` — Portfolio, Position 모델
- `app/domains/portfolios/schema.py` — PortfolioCreate/Response, PositionCreate/Update/Response
- `app/domains/portfolios/repository.py` — PortfolioRepository, PositionRepository
- `app/domains/portfolios/service.py` — PortfolioService
- `app/api/v1/endpoints/portfolios.py` — 5개 엔드포인트
- `app/api/v1/router.py` — portfolios 라우터 등록
- `alembic/env.py` — Portfolio, Position 모델 import 추가
- `alembic/versions/<rev>_create_portfolios_tables.py` — 신규 마이그레이션

## Out of Scope

- 포트폴리오 이름 수정/삭제
- 비중·평가금액 계산, 요약 조회 API (Issue #22)
- 현재가/시세 연동, 평가손익 계산
- 페이지네이션
- CSV/외부 임포트

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`
- `docs/decisions/`

## Requirements

- `portfolios` 테이블: id, user_id(FK users.id, NOT NULL), name(String(255), NOT NULL), created_at, updated_at
- `positions` 테이블: id, portfolio_id(FK portfolios.id, NOT NULL), asset_id(FK assets.id, NOT NULL), quantity(Numeric(20,8), NOT NULL), avg_buy_price(Numeric(20,4), NOT NULL), created_at, updated_at
- unique constraint: `(portfolio_id, asset_id)`
- `PositionUpdate`는 quantity, avg_buy_price를 선택 필드로 받되 최소 1개는 제공되어야 한다.
- 다른 사용자의 portfolio/position에 접근하면 403 반환
- 이미 추가된 종목 중복 추가 시 400 반환
- 존재하지 않는 portfolio/position 접근 시 404 반환
- Alembic `down_revision`은 현재 head revision `9c0d1e23f405`를 참조

## Test Requirements

- `tests/test_portfolios.py` 신규 작성
- 포트폴리오 생성, 목록 조회, 종목 추가, 종목 수정(수량/평균가), 종목 삭제, 소유권 검증(403), 중복 추가(400) 커버리지

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_portfolios.py -v
```

## Documentation Impact

- `docs/designs/021-portfolio-domain.md` 이미 작성됨 (변경 불필요)

## ADR Need

없음. 가격 소스 미도입·매수원가 기준 방침은 설계 021에 기록됨.

## Failure Record Need

없음.

## Risk Level

High — 신규 DB 스키마(2개 테이블), FK 참조, 인증 연동 포함. Human Gate 완료(2026-06-19 사용자 명시적 승인: 매수원가 기준 비중·순차 진행).

## Expected Output

- 위 scope 파일 전체 신규 생성
- `uv run pytest tests/test_portfolios.py` 통과
- lint/typecheck 통과
- PR body에 closing keyword 포함 (`Closes #21`)

## Rules

- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
- 가정과 검증 결과를 보고.
