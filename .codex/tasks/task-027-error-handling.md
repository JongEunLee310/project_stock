# Codex Handoff Task

## Source Issue

Issue #47 (제목 Issue 27): `[BE] 공통 에러 코드 및 예외 처리 구조 정리`

## Task Summary

도메인별 문자열 `ErrorCode` enum을 도입하고, `AppException`에 `error_code`를 추가하며, 예외 핸들러(AppException / RequestValidationError / 미처리 Exception)를 Issue #46 envelope로 통일한다. 기존 모든 `raise AppException(...)` 사이트(~35곳)에 에러 코드를 부여한다.

## Goal

- `app/core/error_codes.py`에 `ErrorCode(str, Enum)`가 존재하고 전 raise 사이트에 매핑된다.
- 모든 에러 응답이 `{data:null, message, error:{code, fields?}, meta:null}` 형식으로 반환된다.
- validation error가 422 + `VALIDATION_ERROR` + 필드 상세로 반환된다.
- 미처리 예외가 500 + `INTERNAL_ERROR`(내부 상세 비노출)로 반환된다.

## Background

- 설계 문서: `docs/designs/027-error-handling.md` (코드↔HTTP↔위치 매핑표 포함).
- **선행 의존: Issue #46(`app/core/response.py` envelope).** #46 머지 후 진행. envelope의 `error`/`message` 필드를 채운다.
- 현행: `app/core/exceptions.py`의 `AppException(status_code, detail)` + `app_exception_handler`가 `{"detail": ...}`만 반환.
- raise 사이트: `grep -rn "AppException" app/domains app/api` 기준 — deps.py, users/assets/watchlists/theses/portfolios/alerts/reports/signals/analysis service.
- HTTPException 직접 사용 없음. 신규 도입 금지, AppException 경유 통일.

## Implementation Scope

- `app/core/error_codes.py` (신규) — `ErrorCode(str, Enum)` (설계 표 기준).
- `app/core/exceptions.py` — `AppException`에 `error_code: ErrorCode` 추가, 핸들러를 envelope 형식으로 변경. (핸들러를 `app/core/handlers.py`로 분리해도 무방.)
- `app/main.py` — `RequestValidationError`, 미처리 `Exception` 핸들러 등록.
- 전 raise 사이트(~35곳) — `error_code` 인자 부여.
- 에러 응답 단언이 있는 기존 테스트 갱신.

## Out of Scope

- 성공 응답 envelope 및 `app/core/response.py` 생성 (Issue #46).
- 신규 도메인/엔드포인트, 비즈니스 로직 변경(상태코드·메시지 의미 불변).
- DB 스키마 변경.
- 로깅 구조 정리 (Issue #42).

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- `ErrorCode` 값 = 이름(대문자 스네이크). 설계 표의 코드를 최소 집합으로 포함하되, 실제 raise 메시지와 1:1 매핑하며 누락 코드는 추가.
- `AppException(status_code, detail, error_code)` — `error_code` 필수 인자(전 호출부 수정 동반). 기본값 두지 않음.
- `app_exception_handler`: status_code + `error_response(code=exc.error_code, message=exc.detail, status=exc.status_code)`.
- `validation_exception_handler`: 422 + `code=VALIDATION_ERROR`, `error.fields`에 필드별 `{loc, msg}` 배열.
- `unhandled_exception_handler`: 500 + `code=INTERNAL_ERROR`, 일반 메시지(스택/내부 상세 미노출).
- 에러 본문 구성은 #46 envelope 재사용(에러 전용 헬퍼 `error_response(...)` 추가 가능, `app/core/response.py`에 둘 것).

## Test Requirements

- 각 핸들러 동작 검증: 도메인 예외(예: 중복 종목 → 400 `ASSET_DUPLICATE`), validation(422 `VALIDATION_ERROR` + fields), 미처리 예외(500 `INTERNAL_ERROR`).
- 기존 테스트의 에러 응답 단언을 `body["error"]["code"]`/`body["message"]` 기준으로 갱신. **약화 금지.**
- 인증 실패(401 `AUTH_INVALID_TOKEN`) 경로 검증.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/027-error-handling.md` 작성됨(변경 불필요).
- ADR: 에러 코드 체계 채택 근거를 `docs/decisions/`에 1건 작성(아래 ADR Need 참조).

## ADR Need

있음(권고) — "도메인별 문자열 ErrorCode 채택" 결정을 `docs/decisions/`에 ADR로 기록. HTTP 일반 코드 대안 대비 선택 사유와 영향 범위를 남긴다. 작성 형식은 기존 `docs/decisions/` 관례를 따른다.

## Failure Record Need

없음.

## Risk Level

Medium — 전 서비스 raise 사이트 수정 + 전역 핸들러 변경. 상태코드·동작은 불변, 응답 본문만 변경. Human Gate 불필요(스키마 변경 없음).

## Expected Output

- `app/core/error_codes.py` 신규, `exceptions.py`/`main.py` 변경, 전 raise 사이트 코드 부여, ADR 1건.
- 테스트 통과, lint/typecheck 통과.
- PR body에 `Closes #47`.

## Rules

- Issue #46(envelope) 머지 후 시작. 미머지 시 중단·보고.
- 비즈니스 로직/상태코드 의미 변경 금지.
- 보호 파일 변경 금지.
- 가정과 검증 결과 보고.
