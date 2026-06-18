# Codex Handoff Task

## Source Issue

Issue #5: 종목 Asset 도메인 구현

## Task Summary

Asset(종목) 도메인을 구현한다. 관심 종목, 뉴스, 리포트, 알림의 기준이 되는 종목 정보를 관리하는 테이블, CRUD API, Alembic 마이그레이션을 포함한다.

## Goal

- 사용자가 종목을 등록할 수 있다.
- 동일 시장의 동일 symbol이 중복 등록되지 않는다.
- 등록된 종목을 목록과 상세로 조회할 수 있다.

## Background

- 기존 users 도메인의 패턴(model/schema/repository/service/endpoint)을 따른다.
- SQLAlchemy 2.x select API, Mapped/mapped_column, DeclarativeBase + TimestampMixin 사용.
- Pydantic v2, from_attributes=True.
- 설계 문서: `docs/designs/005-asset-domain.md`
- Issue #6(Watchlist), Issue #7(InvestmentThesis)의 전제 조건이므로 먼저 완료해야 한다.

## Implementation Scope

- `app/domains/assets/__init__.py`
- `app/domains/assets/model.py` — Asset 모델
- `app/domains/assets/schema.py` — AssetCreate, AssetResponse
- `app/domains/assets/repository.py` — AssetRepository
- `app/domains/assets/service.py` — AssetService
- `app/api/v1/endpoints/assets.py` — 3개 엔드포인트
- `app/api/v1/router.py` — assets 라우터 등록
- `alembic/env.py` — Asset 모델 import 추가
- `alembic/versions/<rev>_create_assets_table.py` — 신규 마이그레이션

## Out of Scope

- 종목 수정/삭제 API
- 인증 연동 (목록/상세는 공개, 등록은 현재 공개로 시작)
- 가격 정보, 외부 API 연동

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`
- `docs/decisions/`

## Requirements

- `assets` 테이블: id(PK), symbol(String 20), name(String 255), market(String 20), is_active(Boolean, default=True), created_at, updated_at
- unique constraint: `(symbol, market)`
- POST /api/v1/assets: symbol+market 중복 시 400 반환
- GET /api/v1/assets: `is_active` 쿼리 파라미터 선택적 필터
- GET /api/v1/assets/{id}: 없으면 404 반환

## Test Requirements

- `tests/test_assets.py` 신규 작성
- TestClient 사용 (httpx)
- 커버리지 대상: 등록 성공, 중복 등록 거부, 목록 조회, 상세 조회, 없는 ID 404

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_assets.py -v
```

## Documentation Impact

- `docs/designs/005-asset-domain.md` 이미 작성됨 (변경 불필요)
- alembic/env.py에 Asset import 추가 사실을 PR description에 명시

## ADR Need

없음. 기존 패턴 적용.

## Failure Record Need

없음.

## Risk Level

High — 신규 DB 스키마 변경 포함. Human Gate 완료(2026-06-18 사용자 명시적 승인).

## Expected Output

- 위 scope 파일 전체 신규 생성
- `uv run pytest tests/test_assets.py` 통과
- lint/typecheck 통과
- PR description에 변경 파일 목록과 verification 결과 포함

## Rules

- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
- 가정 사항과 verification 결과를 PR에 명시.
