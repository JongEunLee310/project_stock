# Codex Handoff Task

## Source Issue

Issue #62 (제목 Issue 42): `[BE] 로깅 구조 정리`

## Task Summary

운영 중 API 요청·에러·외부 provider 호출을 추적할 수 있도록 기본 로깅 구조를 정리한다. request/correlation id, 구조화 로그, 민감 정보 마스킹 기준, 로컬 출력 방식을 도입한다.

## Goal

- API 장애 발생 시 request_id로 요청 흐름을 추적할 수 있다.
- 에러 발생 위치·원인을 로그로 확인할 수 있다.
- 민감 정보(시크릿·토큰)가 로그에 남지 않는다.

## Background

- **설계문서 우선**: `docs/designs/042-logging-structure.md`를 먼저 읽고 따른다.
- 현재 표준 `logging` 미구성. `app/main.py`는 exception handler만 등록하고 에러를 기록하지 않는다.
- 미들웨어는 CORS만 존재. request id 없음.
- 설정은 `app/core/config.py`의 단일 `Settings`(`APP_ENV` 등).

## Implementation Scope

- 로깅 초기화: `setup_logging(settings)` 도입, `create_app`에서 호출(`app/main.py`).
- request id 미들웨어: `X-Request-ID` 수용/생성·응답 헤더 반영, `contextvar`로 로그 레코드에 주입.
- request/response 로그(method, path, status, latency_ms, request_id).
- 에러 로그: `app/core/exceptions.py`의 unhandled/AppException 핸들러에서 원인·request_id 기록(unhandled는 스택 포함).
- provider 호출 로그 구조 준비(요약 수준).
- 민감 키 마스킹 유틸(`SECRET_KEY`, `OPENAI_API_KEY`, `Authorization`, token 등).

## Out of Scope

- 로그 영속화/수집 파이프라인(ELK 등) 연동.
- 별도 로깅 프레임워크(structlog 등) 도입.
- API 응답 envelope 스키마 변경.
- health/scheduler 구현(= #63/#64).

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- request_id가 로그와 응답 헤더에서 일관되게 추적된다.
- 에러 발생 시 원인·위치·request_id가 로그에 남는다.
- 민감 키가 로그 출력에서 마스킹된다.
- 표준 `logging` 사용, `APP_ENV`별 출력 형식 분기.

## Test Requirements

- request id 전파/응답 헤더 테스트.
- 에러 발생 시 로깅 동작 테스트(caplog).
- 마스킹 유틸 단위 테스트.
- 전체 `uv run pytest` 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/042-logging-structure.md`. 환경 변수/로그 형식이 README에 영향 시 갱신(#65에서 통합 정리).

## ADR Need

불필요 — 표준 logging 최소 채택, 아키텍처 결정 없음.

## Failure Record Need

없음.

## Risk Level

Medium — 미들웨어/예외 핸들러 등 시스템 경계 변경. 기존 응답 동작·테스트 보존 필요.

## Expected Output

- 로깅 초기화 + request id 미들웨어 + 에러 로깅 + 마스킹 유틸 + 테스트.
- lint/typecheck/pytest 통과. PR body에 `Closes #62`.

## Rules

- 스코프 유지. 검증 약화 금지.
- 보호 파일 변경 금지.
- API 응답 envelope/스키마 변경 금지.
- 가정과 검증 결과 보고.
