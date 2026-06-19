# project_stock

## 프로젝트 목적

`project_stock`는 투자 리서치와 감시 흐름을 지원하는 FastAPI 기반 MVP입니다.
뉴스 수집, AI 요약, 투자 가설과의 충돌 판단, Signal/Alert 생성, 포트폴리오
집중도 점검을 통해 사람이 투자 판단에 필요한 변화를 빠르게 확인하도록 돕습니다.

## 기술 스택

- Python 3.12, FastAPI, Uvicorn
- SQLAlchemy 2.0, Alembic, PostgreSQL 16
- Redis 7, RQ
- Pydantic Settings, python-dotenv
- python-jose(JWT), passlib[bcrypt]
- OpenAI SDK, feedparser
- uv
- 개발 도구: pytest, pytest-cov, ruff, mypy

## 로컬 실행

의존성을 설치합니다.

```bash
uv sync
```

환경 파일을 준비합니다.

```bash
cp .env.example .env
```

로컬에서 PostgreSQL과 Redis를 직접 실행하는 경우 `.env`의 호스트를 로컬 환경에
맞게 조정합니다. 예를 들어 Docker Compose 밖에서 API를 실행하고 로컬 포트로
접속한다면 `DATABASE_URL`의 호스트는 `localhost`, `REDIS_URL`의 호스트도
`localhost`가 되어야 합니다.

마이그레이션을 적용합니다.

```bash
uv run alembic upgrade head
```

API 서버를 실행합니다.

```bash
uv run uvicorn app.main:app --reload
```

기본 API 주소는 `http://127.0.0.1:8000`이고, 주요 API prefix는 `/api/v1`입니다.

## Docker Compose 실행

API, PostgreSQL, Redis를 함께 실행합니다.

```bash
docker compose up --build
```

Compose 구성의 API 컨테이너는 `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`로
시작하며 호스트의 `8000` 포트에 노출됩니다.

종료합니다.

```bash
docker compose down
```

데이터 볼륨까지 제거하려면 Docker의 볼륨 삭제 옵션을 별도로 사용하세요.

## Alembic

현재 스키마까지 마이그레이션을 적용합니다.

```bash
uv run alembic upgrade head
```

모델 변경 후 새 마이그레이션 초안을 생성합니다.

```bash
uv run alembic revision --autogenerate -m "describe change"
```

생성된 revision은 실제 의도와 일치하는지 검토한 뒤 커밋합니다.

## 테스트 실행

전체 테스트를 실행합니다.

```bash
uv run pytest
```

PR 전 권장 검증 명령은 다음과 같습니다.

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

테스트 구조와 실행 방식의 상세 설명은 [docs/testing.md](docs/testing.md)를 참고하세요.

## 주요 API

모든 라우터는 `/api/v1` 아래에 연결됩니다.
프론트엔드 화면별 연동 명세는 [docs/api/frontend-api-spec.md](docs/api/frontend-api-spec.md)를 참고하세요.

| Prefix | 설명 |
| --- | --- |
| `/api/v1/health` | 서비스 상태 확인 |
| `/api/v1/auth` | 사용자 등록, 로그인, 현재 사용자 조회 |
| `/api/v1/alerts` | 알림 목록 조회, 읽음 처리, 숨김 처리 |
| `/api/v1/assets` | 투자 자산 등록, 목록 조회, 단건 조회 |
| `/api/v1/watchlists` | 관심종목 목록과 항목 관리 |
| `/api/v1/portfolios` | 포트폴리오, 포지션, 집중도 점검 |
| `/api/v1/theses` | 투자 가설 생성, 수정, 조회, 비활성화 |
| `/api/v1/reports` | 리서치 리포트 생성과 조회 |
| `/api/v1/signals` | 투자 시그널 생성과 조회 |
| `/api/v1/job-runs` | 백그라운드 잡 실행 기록 조회 |
| `/api/v1/worker` | 뉴스 수집과 관심종목 분석 잡 enqueue |

## 1차 MVP 범위와 제외

v0.1 MVP 범위는 투자 리서치/감시 흐름입니다. 포함되는 흐름은 뉴스 수집,
AI 요약, 투자 가설 충돌 판단, Signal/Alert 생성, 포트폴리오 집중도 점검입니다.

자동매매(automated trading)는 v0.1 MVP 범위가 아닙니다. 이 프로젝트는 주문 실행,
브로커 연동, 실거래 자동화, 포지션 자동 조정 기능을 제공하지 않습니다.
