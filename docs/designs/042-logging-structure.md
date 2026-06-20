# 042 Logging Structure

## Scope

운영 중 문제를 추적할 수 있도록 기본 로깅 구조를 정리한다. request/correlation id, API 요청·에러 로그 구조, 외부 provider 호출 로그 준비, 민감 정보 마스킹 기준, 로컬 개발 환경 출력 방식을 정의한다. 신규 도메인/스키마 변경은 없다. 외부 로그 수집 파이프라인(ELK 등) 연동은 후속 버전으로 분리한다.

## Current State

- 표준 `logging` 미구성. `app/main.py`는 exception handler만 등록하고 에러를 기록하지 않는다(`unhandled_exception_handler`).
- 미들웨어는 CORS만 존재. request id/correlation id 없음.
- 외부 provider 호출(`app/adapters/*`)에 대한 로깅 없음.

## Structure

| 영역 | 책임 |
| --- | --- |
| logging config | 단일 진입점에서 log level/format 구성. `APP_ENV`별 출력(dev: 사람이 읽기 쉬운 형태, prod: 구조화). |
| request id middleware | 요청마다 correlation id 생성, `X-Request-ID` 헤더 수용/전파, 응답 헤더에 반영. |
| request/response log | method, path, status, latency_ms, request_id. |
| error log | unhandled/AppException 발생 위치·원인·request_id 기록. |
| provider call log | adapter 호출 시작/실패를 요약 수준으로 남길 구조 준비. |
| masking | `SECRET_KEY`, `OPENAI_API_KEY`, `Authorization`, token 등 민감 키 마스킹 기준. |

## Functions (시그니처 + 책임)

- `setup_logging(settings) -> None`: 로깅 핸들러/포맷 초기화. `create_app`에서 호출.
- request id middleware: `contextvar` 기반으로 request_id 보관하고 로그 레코드에 주입.
- 에러 핸들러 보강: `unhandled_exception_handler` / `app_exception_handler`에서 `logger` 기록(원인·request_id, unhandled는 스택 포함).

## Decisions

- 표준 라이브러리 `logging`을 사용한다 — 별도 로깅 프레임워크(structlog 등)는 도입하지 않는다(ADR 불필요 수준의 최소 채택).
- 마스킹은 민감 키 블랙리스트로 시작한다(키 목록 기반).
- 로그 영속화/수집 파이프라인은 범위 외.
- request_id는 로깅 추적용이며 API 응답 envelope 스키마는 변경하지 않는다.
