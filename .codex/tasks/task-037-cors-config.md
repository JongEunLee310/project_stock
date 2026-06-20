# Codex Handoff Task

## Source Issue

Issue #57 (제목 Issue 37): `[BE] CORS 및 프론트엔드 개발 환경 설정`

## Task Summary

로컬 프론트엔드 개발 서버와 백엔드가 통신하도록 CORS를 설정한다. 허용 origin을 환경 변수 기반으로 주입(하드코딩 금지)하고 개발/운영 설정을 분리한다. 이 작업은 #58에서 정리한 설정 구조 위에 CORS 항목을 추가한다.

## Goal

- 로컬 프론트엔드에서 API 호출이 정상 동작한다.
- CORS origin이 하드코딩되어 있지 않다(전적으로 settings에서 읽음).
- 개발/운영 환경별 설정이 분리된다.

## Background

- **설계문서 우선**: `docs/designs/037-cors-config.md`를 먼저 읽고 따른다. 구현 중 달라지면 갱신.
- **선행 의존성**: #58(`docs/designs/038-config-structure.md`)이 `Settings`/`APP_ENV`/`.env.example`을 정리한 뒤 진행한다. 그 위에 CORS 설정 항목을 추가한다(중복 정의 금지).
- 현재 `app/main.py`에 `CORSMiddleware` 미적용, `app/core/config.py`에 CORS 항목 없음.
- 글로벌 원칙: 설정은 env 기반, 민감/환경 의존 값 하드코딩 금지.

## Implementation Scope

- `app/core/config.py` — `CORS_ORIGINS`(`list[str]`, env 콤마 구분 파싱), `CORS_ALLOW_CREDENTIALS`(`bool`) 추가.
- `app/main.py` — `CORSMiddleware`를 `settings.CORS_ORIGINS`/`CORS_ALLOW_CREDENTIALS` 기반으로 등록.
- `.env.example` — `CORS_ORIGINS` 항목 + 개발/운영 예시 주석 추가.
- `docs/designs/037-cors-config.md` — 달라지면 갱신.
- `docs/api/frontend-api-spec.md` — CORS/허용 origin 예시 문서화(필요 시).

## Out of Scope

- 인증 쿠키/세션 도입(credentials 기본 off로 시작).
- 운영 인프라/배포 설정 변경.
- 프론트엔드 코드.

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- 허용 origin은 `settings.CORS_ORIGINS`에서만 읽고 코드에 origin 리터럴을 두지 않는다.
- 개발 기본값 예시(`http://localhost:3000`, `http://localhost:5173`)는 env/example로 제공.
- `allow_origins=["*"]` + `allow_credentials=True` 동시 사용 금지.
- preflight(OPTIONS)는 `CORSMiddleware` 자동 처리에 위임.

## Test Requirements

- 허용 origin 요청 시 CORS 응답 헤더(`access-control-allow-origin`) 포함 테스트.
- preflight(OPTIONS) 요청 동작 테스트.
- `CORS_ORIGINS`가 settings에서 주입됨을 확인하는 테스트(하드코딩 아님).
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/037-cors-config.md`, `docs/api/frontend-api-spec.md`(허용 origin 예시).
- `.env.example` 갱신.

## ADR Need

불필요 — 표준 CORS 미들웨어 설정. 단, credentials 정책을 향후 인증 연동 시 재검토(설계문서에 명시).

## Failure Record Need

없음.

## Risk Level

Low — 미들웨어 1개 추가 + 설정 항목. 기능 로직 변경 없음.

## Expected Output

- CORS 미들웨어 + 설정 항목 + `.env.example` + 테스트.
- lint/typecheck/pytest 통과. PR body에 `Closes #57`.

## Rules

- origin 하드코딩 금지(전적으로 settings).
- #58 설정 구조와 중복 정의 금지.
- 보호 파일 변경 금지.
- 가정(개발 기본 origin, credentials off)과 검증 결과 보고.
