# Backend v0.2 Integration Guide

이 문서는 Backend v0.2 기준으로 로컬 실행, API 호출, provider 전환, 프론트엔드 연동 주의사항, 테스트 실행을 한 번에 따라가기 위한 진입점이다. 상세 API 카탈로그는 [Frontend API Spec](api/frontend-api-spec.md), 테스트 세부 사항은 [Testing](testing.md)을 기준으로 한다.

## Quick Start

의존성을 설치하고 로컬 환경 파일을 만든다.

```bash
uv sync
cp .env.example .env
```

PostgreSQL과 Redis는 Docker Compose로 함께 띄우거나 로컬 서비스를 직접 사용할 수 있다.

```bash
docker compose up --build
```

API를 컨테이너 밖에서 직접 실행한다면 `.env`의 DB/Redis 호스트를 로컬 포트에 맞춘다.

```dotenv
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/stock_db
REDIS_URL=redis://localhost:6379/0
```

마이그레이션을 적용하고 서버를 실행한다.

```bash
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

기본 주소는 `http://127.0.0.1:8000`이고, 주요 API prefix는 `/api/v1`이다. 상태 확인은 monitoring 호환을 위해 공통 envelope를 쓰지 않는다.

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/health/readiness
```

## Environment

설정은 [app/core/config.py](../app/core/config.py)의 `Settings`가 `.env`와 프로세스 환경 변수에서 로드한다. 로컬 예시는 [.env.example](../.env.example)을 복사해서 시작한다.

| Variable | Default | Notes |
| --- | --- | --- |
| `APP_ENV` | `dev` | `dev`, `test`, `prod` 중 하나. |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/stock_db` | Compose 내부에서는 `.env.example`처럼 host가 `db`다. |
| `REDIS_URL` | `redis://localhost:6379/0` | Compose 내부에서는 host가 `redis`다. |
| `SECRET_KEY` | `change-me-in-production` | 실제 환경에서는 반드시 비밀 값으로 주입한다. |
| `ALGORITHM` | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 로그인 token 만료 시간. |
| `OPENAI_API_KEY` | empty / `None` | mock-only 로컬 흐름에서는 비워둘 수 있다. |
| `LLM_TIMEOUT_SECONDS` | `30` | LLM 호출 timeout. |
| `MARKET_PROVIDER` | `mock` | `mock` 또는 `real`. |
| `NEWS_PROVIDER` | `mock` | `mock` 또는 `real`. |
| `DISCLOSURE_PROVIDER` | `mock` | `mock` 또는 `real`. |
| `PORTFOLIO_PROVIDER` | `mock` | `mock` 또는 `real`. |
| `CORS_ORIGINS` | empty list | 콤마 구분 origin. 예: `http://localhost:3000,http://localhost:5173`. |
| `CORS_ALLOW_CREDENTIALS` | `false` | `true`일 때 `CORS_ORIGINS=*` 조합은 설정 검증에서 거부된다. |

민감 정보는 커밋하지 말고 로컬 `.env`, CI secret, 배포 환경 변수로 주입한다. `.env.example`에는 placeholder와 로컬 기본값만 둔다.

## Provider Modes

Provider 전환은 `*_PROVIDER` 환경 변수로 한다.

```dotenv
MARKET_PROVIDER=mock
NEWS_PROVIDER=mock
DISCLOSURE_PROVIDER=mock
PORTFOLIO_PROVIDER=mock
```

`mock`은 deterministic adapter를 사용해 외부 증권, 뉴스, 공시, 포트폴리오 API 없이 로컬 개발과 테스트를 반복할 수 있게 한다. `real` 값은 설정 타입상 허용되지만 현재 [app/adapters/factory.py](../app/adapters/factory.py)에서 실제 구현이 없는 provider는 `NotImplementedError`로 실패한다. 실제 provider 연결은 후속 작업 범위다.

현재 provider mode는 readiness 응답에서 확인할 수 있다.

```bash
curl http://127.0.0.1:8000/api/v1/health/readiness
```

## API Flow

프론트엔드 연동용 전체 화면 매핑과 요청/응답 예시는 [Frontend API Spec](api/frontend-api-spec.md)을 기준으로 한다. 모든 `/api/v1` 응답은 별도 표기가 없는 한 다음 envelope를 사용한다.

```json
{
  "data": {},
  "message": null,
  "error": null,
  "meta": null
}
```

인증이 필요한 API는 `Authorization: Bearer <access_token>` 헤더를 보낸다.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret1234"}'

curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret1234"}'
```

로그인 응답의 `data.access_token`을 사용해 사용자 범위 리소스를 호출한다.

```bash
TOKEN="<access_token>"

curl http://127.0.0.1:8000/api/v1/auth/me \
  -H "Authorization: Bearer ${TOKEN}"

curl "http://127.0.0.1:8000/api/v1/watchlists?page=1&size=20" \
  -H "Authorization: Bearer ${TOKEN}"
```

종목 기본 조회와 일부 상세 API는 인증 없이 호출할 수 있다.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/assets \
  -H "Content-Type: application/json" \
  -d '{"symbol":"AAPL","name":"Apple Inc.","market":"NASDAQ"}'

curl http://127.0.0.1:8000/api/v1/assets/1/detail
```

작업 enqueue와 scheduler 수동 실행은 `/api/v1/worker` 아래에 있다. RQ 작업 enqueue에는 Redis가 필요하다.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/worker/jobs/news \
  -H "Content-Type: application/json" \
  -d '{"symbols":["AAPL"]}'

curl -X POST http://127.0.0.1:8000/api/v1/worker/scheduler/jobs/mock_collection/run
```

## Domain Map

핵심 도메인 설계는 `docs/designs/`에 남아 있다. 구현을 깊게 읽기 전에 아래 문서를 먼저 확인한다.

| Domain | Runtime surface | Design links |
| --- | --- | --- |
| Assets | `/api/v1/assets`, market mock quote, buy checklist, research summary | [005](designs/005-asset-domain.md), [031](designs/031-asset-basic-info-api.md), [032](designs/032-research-summary-api.md), [033](designs/033-decision-checklist-api.md) |
| Watchlists | `/api/v1/watchlists`, watchlist analysis input | [006](designs/006-watchlist-domain.md), [030](designs/030-watchlist-api-improvement.md) |
| News and analysis | news adapters, raw/news items, reports, thesis conflict flow | [010](designs/010-news-adapter.md), [014](designs/014-news-ai-summary.md), [015](designs/015-thesis-conflict-analysis.md), [019](designs/019-watchlist-analysis-flow.md) |
| Signals and alerts | `/api/v1/signals`, `/api/v1/alerts`, `/api/v1/alert-candidates` | [017](designs/017-signal-domain.md), [018](designs/018-alert-domain.md), [035](designs/035-alert-candidate-api.md) |
| Portfolios | `/api/v1/portfolios`, concentration check | [021](designs/021-portfolio-domain.md), [022](designs/022-portfolio-concentration.md), [034](designs/034-portfolio-summary-api.md) |
| Jobs and scheduler | `/api/v1/job-runs`, `/api/v1/worker/*`, scheduler skeleton | [011](designs/011-worker-background-job.md), [012](designs/012-job-runs-domain.md), [044](designs/044-scheduler-skeleton.md) |

## Frontend Notes

- 목록 API는 `page >= 1`, `size` 기본값 `20`, 최대 `100`을 사용하며 목록 응답의 `meta`는 `{ "page": 1, "size": 20, "total": 1 }` 형태다.
- 정렬을 지원하는 목록은 `sort=field` 또는 `sort=-field`를 사용한다. 허용되지 않은 field는 `422 VALIDATION_ERROR`다.
- 실패 응답은 `data: null`, `meta: null`, `error.code`를 포함한다. 대표 error shape과 계약 변경 기준은 [Frontend API Spec](api/frontend-api-spec.md)의 Auth, Contract 섹션을 따른다.
- `/health`와 `/api/v1/health`는 monitoring 호환 때문에 envelope를 사용하지 않는다. 앱 내부 readiness는 `/api/v1/health/readiness`를 사용한다.
- 브라우저 프론트엔드는 `CORS_ORIGINS`에 개발 서버 origin을 명시한다. credential 동반 요청이 필요하면 `CORS_ALLOW_CREDENTIALS=true`와 명시 origin 목록을 함께 사용한다.
- 응답에는 `X-Request-ID`가 포함된다. 프론트/백엔드 로그를 맞출 때 같은 값을 전달하거나 응답 헤더 값을 기록한다.

## Testing

문서와 API 계약을 확인한 뒤 기본 검증을 실행한다.

```bash
uv run ruff check .
uv run pytest
```

PR 전 전체 권장 검증에는 type check도 포함한다.

```bash
uv run mypy .
```

테스트는 기본적으로 in-memory SQLite fixture를 사용하므로 외부 DB, Redis, worker process 없이 대부분의 suite를 실행할 수 있다. 자세한 내용은 [Testing](testing.md)을 참고한다.

## Related Docs

- [README](../README.md): 프로젝트 개요, 로컬 실행, 주요 API 목록.
- [Frontend API Spec](api/frontend-api-spec.md): 화면별 API 매핑과 구현 API catalog.
- [Testing](testing.md): 테스트 구조와 실행 방식.
- [036 List Query Conventions](designs/036-list-query-conventions.md): pagination/sort 규칙.
- [037 CORS Config](designs/037-cors-config.md): CORS 설정 결정.
- [038 Config Structure](designs/038-config-structure.md): 환경 변수와 설정 구조.
- [039 DB Migration Structure](designs/039-db-migration-structure.md): Alembic 운영 규칙.
- [045 Backend v0.2 Integration Docs](designs/045-backend-v0.2-docs.md): 이 문서 작업의 설계 기록.
