# Codex Handoff Task

## Source Issue

Issue #25: 기본 README 및 개발 실행 문서 작성

## Task Summary

현행 `README.md`는 프로젝트가 아니라 Harness Engineering 템플릿을 설명하며, "automated system for stock trading"이라는 서술은 본 MVP의 자동매매 제외 방침과 모순된다. 개발자가 clone 후 README만으로 로컬 실행·테스트할 수 있도록 프로젝트 실 문서로 전면 재작성한다.

## Goal

- README만 보고 로컬 실행이 가능하도록 목적/스택/실행/마이그레이션/테스트/API/MVP 범위를 문서화한다.
- 자동매매가 v0.1 MVP 범위에 포함되지 않음을 명시한다.

## Background

- 설계 문서: `docs/designs/025-project-readme.md`
- 환경 변수: `.env.example` — `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`.
- `docker-compose.yml`: `api`(포트 8000, `uv run uvicorn app.main:app --reload`), `db`(postgres:16-alpine), `redis`(7-alpine).
- `alembic.ini` + `alembic/versions` 존재.
- API 라우터 `app/api/v1/router.py`(prefix `/api/v1`): health, auth, alerts, assets, watchlists, portfolios, theses, reports, signals, job-runs, worker.
- 테스트 문서는 `docs/testing.md`(이미 존재) — README에서 링크만.
- 의존성(`pyproject.toml`): FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL(psycopg2), Redis+RQ, Pydantic Settings, python-jose(JWT), passlib[bcrypt], openai, feedparser, uv. Dev: pytest, pytest-cov, ruff, mypy.

## Implementation Scope

- `README.md` (전면 재작성). 아래 섹션을 Issue #25 작업 항목 순서로 작성:
  1. 프로젝트 목적 — 투자 리서치/감시 MVP(뉴스 수집 → AI 요약 → 투자 가설 충돌 판단 → Signal/Alert, 포트폴리오 집중도 점검).
  2. 기술 스택 — 위 의존성 목록 기반.
  3. 로컬 실행 — `uv sync`, `.env`를 `.env.example`에서 복사, PostgreSQL/Redis 준비, `uv run alembic upgrade head`, `uv run uvicorn app.main:app --reload`.
  4. Docker Compose 실행 — `docker compose up --build`, 종료 `docker compose down`.
  5. Alembic — `uv run alembic upgrade head`, `uv run alembic revision --autogenerate -m "..."`.
  6. 테스트 실행 — `uv run pytest`, 상세는 `docs/testing.md` 링크.
  7. 주요 API 목록 — 위 11개 라우터를 prefix와 한 줄 설명으로 표 또는 목록.
  8. 1차 MVP 범위와 제외 — 포함: 리서치/감시 흐름. **제외: 자동매매(automated trading)는 v0.1 MVP 범위 아님**을 명시.
- 기존 템플릿/하니스 설명(Claude·Codex 역할, "How To Use", "Included Practices" 등)은 README 본문에서 제거. 필요 시 `docs/` 링크만 유지.

## Out of Scope

- 프로덕션 코드/스키마/엔드포인트 변경.
- `docs/testing.md` 재작성(링크만).
- 신규 기능/엔드포인트 추가.
- README에 실제와 다른 명령·경로 기재 금지(존재하는 파일/스크립트와 일치해야 함).

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Test Requirements

- 문서 변경이므로 신규 테스트 없음.
- `uv run pytest` 전체 통과 유지(회귀 없음 확인).
- README에 기재한 명령이 실제 프로젝트 구성(`uv`, `alembic.ini`, `docker-compose.yml`, 라우터 prefix)과 일치하는지 확인.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `README.md` 전면 재작성.
- `docs/designs/025-project-readme.md` 이미 작성됨 (변경 불필요).

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Low — 문서 한정. 코드·스키마·보호 파일 변경 없음. Human Gate 불필요.

## Expected Output

- 프로젝트 README 전면 재작성(위 8개 섹션, 자동매매 제외 명시).
- `uv run pytest`/lint/typecheck 통과(회귀 없음).
- PR body에 closing keyword 포함 (`Closes #25`).

## Rules

- 스코프 외(프로덕션 코드) 변경 금지.
- 보호 파일 변경 금지.
- 실제와 다른 명령·경로 기재 금지.
- 가정과 검증 결과를 보고.
