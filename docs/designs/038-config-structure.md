# 038 Environment Variable and Config Structure

## Scope

개발/테스트/운영 환경 설정을 분리하고 민감 정보가 코드에 포함되지 않도록 설정 구조를 정리한다. `.env.example`을 현재 `Settings`와 일치하도록 보강하고, 환경 식별자(`APP_ENV`)와 mock/real provider 전환 옵션을 명확히 한다. DB 연결 정보·외부 API key는 placeholder로만 노출한다. 이 작업은 #57(CORS)·#59(마이그레이션)가 의존하는 설정 기반이므로 가장 먼저 진행한다.

## Current State

- `app/core/config.py` — `pydantic-settings` `Settings`(`env_file=".env"`, `extra="ignore"`). `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `OPENAI_API_KEY`, `LLM_TIMEOUT_SECONDS`, `MARKET/NEWS/DISCLOSURE/PORTFOLIO_PROVIDER`(`mock`/`real`).
- `.env.example` — 일부 변수 누락(`OPENAI_API_KEY`, `LLM_TIMEOUT_SECONDS` 등 미기재).
- `.gitignore` — `.env*` 무시, `!.env.example` 예외. 민감 파일 추적 안전.

## Config

| Setting | Type | Default | Notes |
| --- | --- | --- | --- |
| `APP_ENV` | `Literal["dev","test","prod"]` | `"dev"` | 환경 식별. 신규 추가 |
| `DATABASE_URL` | `str` | dev placeholder | 운영은 env 주입 |
| `REDIS_URL` | `str` | dev placeholder | |
| `SECRET_KEY` | `str` | placeholder | 운영은 반드시 env 주입 |
| `OPENAI_API_KEY` | `str \| None` | `None` | placeholder만, 실제 키 커밋 금지 |
| `*_PROVIDER` | `Literal["mock","real"]` | `mock` | mock/real 전환 |

(기존 항목 유지, 위는 정리·추가 대상 중심.)

## Functions

- `app/core/config.py` — `APP_ENV` 추가. 단일 `Settings` 클래스 유지(환경별 서브클래스 도입하지 않음). 필요한 검증(예: prod에서 placeholder SECRET_KEY 경고)은 최소 범위로만.
- `.env.example` — 현재 `Settings`의 모든 변수를 placeholder/주석과 함께 망라. 신규 개발자가 이 파일만으로 로컬 구성 가능하도록.

## Decisions

- 환경별 설정은 `APP_ENV` 단일 변수 + 환경별 `.env`로 처리 — 환경별 Settings 서브클래스/다중 config 파일은 현 단계 과한 복잡도라 도입하지 않는다.
- 민감 정보는 `.env.example`에 placeholder만 — 실제 값은 git 비추적 `.env`(이미 `.gitignore` 처리됨).
- mock/real 전환은 기존 provider 변수를 그대로 사용 — 어댑터 팩토리(`app/adapters/factory.py`)와의 연결은 변경하지 않는다.
- CORS 관련 설정 항목은 본 구조 위에 #57에서 추가한다.
