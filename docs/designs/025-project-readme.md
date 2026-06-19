# 025. 프로젝트 README 및 개발 실행 문서 (Issue #25)

## 배경

현행 `README.md`는 프로젝트가 아니라 Harness Engineering **템플릿**을 설명한다(Claude/Codex 역할, 템플릿 사용법). line 3 "A project of automated system for stock trading."는 본 MVP가 **자동매매를 제외**한다는 Issue #25 요구와 모순된다. 개발자가 clone 후 README만으로 로컬 실행·테스트할 수 있도록 프로젝트 실 문서로 전면 재작성한다.

## 수집된 사실 (재작성 근거)

- 기술 스택: FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, Redis 7 + RQ, Pydantic Settings, python-jose(JWT), passlib[bcrypt], openai, feedparser, uv. Dev: pytest, pytest-cov, ruff, mypy.
- 환경 변수(`.env.example`): `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`.
- Docker Compose(`docker-compose.yml`): `api`(8000), `db`(postgres:16), `redis`(7). `api`는 `uv run uvicorn app.main:app --reload`로 기동.
- Alembic: `alembic.ini` 존재, `alembic/versions`.
- API 라우터(`app/api/v1/router.py`, prefix `/api/v1`): health, auth, alerts, assets, watchlists, portfolios, theses, reports, signals, job-runs, worker.
- 테스트: `docs/testing.md`(Issue #23에서 작성), SQLite in-memory, 외부 의존 없음.

## 변경 사항

### README.md (전면 재작성)
Issue #25 작업 항목 순서로 구성:
1. **프로젝트 목적** — 투자 리서치/감시 MVP(뉴스 수집 → AI 요약 → 투자 가설 충돌 판단 → Signal/Alert, 포트폴리오 집중도 점검).
2. **기술 스택** — 위 목록.
3. **로컬 실행** — `uv sync` → `.env`(`.env.example` 복사) → PostgreSQL/Redis 준비 → `uv run alembic upgrade head` → `uv run uvicorn app.main:app --reload`.
4. **Docker Compose 실행** — `docker compose up --build`(api/db/redis 동시 기동), 종료 `docker compose down`.
5. **Alembic** — `uv run alembic upgrade head`(적용), `uv run alembic revision --autogenerate -m "..."`(생성).
6. **테스트 실행** — `uv run pytest`, 상세는 `docs/testing.md` 링크.
7. **주요 API 목록** — `/api/v1/{health,auth,alerts,assets,watchlists,portfolios,theses,reports,signals,job-runs,worker}` 한 줄 설명 표.
8. **MVP 범위와 제외** — 포함: 리서치/감시 흐름. **제외: 자동매매(automated trading)는 v0.1 MVP 범위 아님**을 명시.

기존 템플릿/하니스 설명(Claude·Codex 역할, How To Use)은 README에서 제거하고, 필요 시 `docs/`로의 링크만 남긴다.

## 범위 밖

- 프로덕션 코드/스키마/엔드포인트 변경.
- `docs/testing.md` 재작성(링크만).
- 신규 기능/엔드포인트 추가.

## 보호 파일

`AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## 검증

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```
(문서 변경이므로 코드 검증은 무영향 확인 용도. README의 명령은 실제 파일/스크립트와 일치해야 함.)

## Risk Level

Low — 문서 한정. 코드·스키마·보호 파일 변경 없음. Human Gate 불필요.

## ADR / Failure Record

불필요.
