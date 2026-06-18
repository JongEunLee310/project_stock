# Codex Handoff Task

## Source Issue

Issue #6: 관심 종목 Watchlist 도메인 구현

## Task Summary

Watchlist(관심 목록) 도메인을 구현한다. 사용자가 감시할 종목 목록을 생성하고 관리하는 테이블, CRUD API, Alembic 마이그레이션을 포함한다.

## Goal

- 사용자가 관심 목록을 생성할 수 있다.
- 관심 목록에 종목을 추가할 수 있다.
- 관심 목록에서 종목을 제거할 수 있다.
- 사용자별 관심 목록이 분리된다.

## Background

- Issue #5(Asset 도메인)가 완료된 후에 진행한다. assets 테이블이 존재해야 한다.
- 인증된 사용자만 접근 가능 — `app/api/v1/deps.py`의 `get_current_user` 사용.
- 사용자 소유권 검증 필수: 다른 사용자의 watchlist 접근 불가.
- 설계 문서: `docs/designs/006-watchlist-domain.md`

## Implementation Scope

- `app/domains/watchlists/__init__.py`
- `app/domains/watchlists/model.py` — Watchlist, WatchlistItem 모델
- `app/domains/watchlists/schema.py` — WatchlistCreate/Response, WatchlistItemCreate/Response
- `app/domains/watchlists/repository.py` — WatchlistRepository, WatchlistItemRepository
- `app/domains/watchlists/service.py` — WatchlistService
- `app/api/v1/endpoints/watchlists.py` — 4개 엔드포인트
- `app/api/v1/router.py` — watchlists 라우터 등록
- `alembic/env.py` — Watchlist, WatchlistItem 모델 import 추가
- `alembic/versions/<rev>_create_watchlists_tables.py` — 신규 마이그레이션

## Out of Scope

- 관심 목록 이름 수정/삭제
- 우선순위 정렬 API
- 페이지네이션

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`
- `docs/decisions/`

## Requirements

- `watchlists` 테이블: id, user_id(FK users.id), name, created_at, updated_at
- `watchlist_items` 테이블: id, watchlist_id(FK watchlists.id), asset_id(FK assets.id), priority(default=0), created_at, updated_at
- unique constraint: `(watchlist_id, asset_id)`
- 다른 사용자의 watchlist에 접근하면 403 반환
- 이미 추가된 종목 중복 추가 시 400 반환
- Alembic `down_revision`은 assets 마이그레이션 revision ID를 참조

## Test Requirements

- `tests/test_watchlists.py` 신규 작성
- 목록 생성, 목록 조회, 종목 추가, 종목 삭제, 소유권 검증 커버리지

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_watchlists.py -v
```

## Documentation Impact

- `docs/designs/006-watchlist-domain.md` 이미 작성됨 (변경 불필요)

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

High — 신규 DB 스키마 변경, FK 참조, 인증 연동 포함. Human Gate 완료(2026-06-18 사용자 명시적 승인).

## Expected Output

- 위 scope 파일 전체 신규 생성
- `uv run pytest tests/test_watchlists.py` 통과
- lint/typecheck 통과

## Rules

- Issue #5 완료 후 진행.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
