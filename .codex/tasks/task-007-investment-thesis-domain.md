# Codex Handoff Task

## Source Issue

Issue #7: 투자 가설 Investment Thesis 도메인 구현

## Task Summary

InvestmentThesis(투자 가설) 도메인을 구현한다. 종목을 왜 감시하는지, 어떤 조건에서 가설이 깨지는지를 기록하는 테이블, CRUD API, Alembic 마이그레이션을 포함한다.

## Goal

- 사용자가 종목별 투자 가설을 작성할 수 있다.
- 사용자가 리스크 요인과 무효화 조건을 작성할 수 있다.
- 시스템이 종목별 최신 투자 가설을 조회할 수 있다.

## Background

- Issue #5(Asset 도메인)가 완료된 후에 진행한다. assets 테이블이 존재해야 한다.
- Issue #6과 독립적으로 진행 가능 (공통 전제는 Issue #5).
- 인증된 사용자만 접근 가능 — `app/api/v1/deps.py`의 `get_current_user` 사용.
- 소유권 검증 필수.
- 설계 문서: `docs/designs/007-investment-thesis-domain.md`

## Implementation Scope

- `app/domains/theses/__init__.py`
- `app/domains/theses/model.py` — InvestmentThesis 모델
- `app/domains/theses/schema.py` — ThesisCreate, ThesisUpdate, ThesisResponse
- `app/domains/theses/repository.py` — ThesisRepository
- `app/domains/theses/service.py` — ThesisService
- `app/api/v1/endpoints/theses.py` — 4개 엔드포인트
- `app/api/v1/router.py` — theses 라우터 등록
- `alembic/env.py` — InvestmentThesis 모델 import 추가
- `alembic/versions/<rev>_create_investment_theses_table.py` — 신규 마이그레이션

## Out of Scope

- AI 분석 연동 (Issue #14, #15에서 다룸)
- 가설 삭제 (deactivate로 대체)
- 가설 목록 페이지네이션

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`
- `docs/decisions/`

## Requirements

- `investment_theses` 테이블: id, user_id(FK users.id), asset_id(FK assets.id), summary(Text), risk_factors(Text nullable), invalidation_conditions(Text nullable), is_active(Boolean default=True), created_at, updated_at
- 인덱스: `ix_investment_theses_asset_id`
- GET /api/v1/theses/latest?asset_id=: 해당 사용자의 가장 최근 is_active=True 가설 반환, 없으면 404
- PUT: 소유권 검증, 없으면 404
- PATCH /deactivate: is_active=False 처리
- Alembic `down_revision`은 assets 마이그레이션 revision ID를 참조

## Test Requirements

- `tests/test_theses.py` 신규 작성
- 가설 생성, 수정, 최신 조회, 비활성화, 소유권 검증 커버리지

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_theses.py -v
```

## Documentation Impact

- `docs/designs/007-investment-thesis-domain.md` 이미 작성됨 (변경 불필요)

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

High — 신규 DB 스키마 변경, FK 참조, 인증 연동 포함. Human Gate 완료(2026-06-18 사용자 명시적 승인).

## Expected Output

- 위 scope 파일 전체 신규 생성
- `uv run pytest tests/test_theses.py` 통과
- lint/typecheck 통과

## Rules

- Issue #5 완료 후 진행.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
