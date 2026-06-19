# Design: 공통 에러 코드 및 예외 처리 구조 (Issue #47 / 제목 Issue 27)

API 예외 상황을 일관된 JSON으로 반환하고, 프론트엔드가 에러 코드(분기용)와 메시지(표시용)를 분리해 사용할 수 있도록 공통 에러 코드 체계와 예외 핸들러를 정리한다. Issue #46의 응답 envelope `error` 필드를 채운다.

## 에러 응답 형식 (envelope의 error 필드)

```
{
  "data": null,
  "message": "<사용자 표시용 메시지>",
  "error": { "code": "<ErrorCode>", "fields": [ ... ]? },
  "meta": null
}
```

- `error.code`: 아래 `ErrorCode` enum 값(문자열). 프론트 분기 키.
- `message`: 기존 `AppException.detail` 사용자 메시지.
- `error.fields`: validation error일 때만 포함(필드별 사유 배열).

## 신규 모듈: app/core/error_codes.py

`ErrorCode(str, Enum)` — 도메인 접두 + 의미 기반 문자열. (값 = 이름)

| 코드 | HTTP | 발생 위치(현행 raise) |
|------|------|----------------------|
| VALIDATION_ERROR | 422 | RequestValidationError |
| AUTH_INVALID_TOKEN | 401 | deps.get_current_user |
| AUTH_USER_NOT_FOUND | 401 | deps.get_current_user |
| AUTH_INVALID_CREDENTIALS | 401 | users.service 로그인 |
| USER_EMAIL_DUPLICATE | 400 | users.service 등록 |
| ASSET_DUPLICATE | 400 | assets.service |
| ASSET_NOT_FOUND | 404 | assets.service |
| WATCHLIST_NOT_FOUND | 404 | watchlists.service |
| WATCHLIST_ITEM_DUPLICATE | 400 | watchlists.service |
| WATCHLIST_FORBIDDEN | 403 | watchlists.service |
| THESIS_NOT_FOUND | 404 | theses.service |
| THESIS_FORBIDDEN | 403 | theses.service |
| PORTFOLIO_NOT_FOUND | 404 | portfolios.service |
| PORTFOLIO_FORBIDDEN | 403 | portfolios.service |
| POSITION_NOT_FOUND | 404 | portfolios.service |
| POSITION_DUPLICATE | 400 | portfolios.service |
| ALERT_NOT_FOUND | 404 | alerts.service |
| REPORT_NOT_FOUND | 404 | reports.service |
| SIGNAL_NOT_FOUND | 404 | signals.service |
| ANALYSIS_ERROR | 4xx | analysis.service |
| INTERNAL_ERROR | 500 | 처리되지 않은 예외 |

> 표는 현행 raise 사이트(`grep AppException`) 기준 초기 집합. 핸드오프 구현 시 실제 메시지와 1:1 매핑하여 확정한다.

## AppException 확장 (app/core/exceptions.py)

- 기존: `AppException(status_code, detail)`.
- 변경: `AppException(status_code, detail, error_code: ErrorCode)` — `error_code` 필드 추가.
- 하위호환을 위해 `error_code` 기본값을 status 기반 일반 코드로 둘지, 전 호출부 필수 인자로 둘지 핸드오프에서 결정(전 호출부 35곳 수정 동반).

## 예외 핸들러

`main.py`에 등록할 핸들러(모듈 위치: `app/core/exceptions.py` 또는 신규 `app/core/handlers.py`).

- `app_exception_handler(AppException)` → status_code + envelope(`message=detail`, `error.code=error_code`).
- `validation_exception_handler(RequestValidationError)` → 422 + envelope(`code=VALIDATION_ERROR`, `error.fields`=필드별 `{loc, msg}` 정리).
- `unhandled_exception_handler(Exception)` → 500 + envelope(`code=INTERNAL_ERROR`, 일반 메시지). 내부 상세 미노출.

응답 본문 구성은 Issue #46의 envelope 구조를 재사용한다(에러 전용 헬퍼 `error_response(code, message, status, fields=None)` 추가 검토).

## 적용 (기존 raise 사이트 ~35곳)

- `app/api/v1/deps.py`, `app/domains/*/service.py`, `app/domains/analysis/service.py`의 모든 `raise AppException(...)`에 `error_code` 부여.
- HTTPException 직접 사용 없음(현행 전부 AppException) — 신규 도입 금지, AppException 경유 통일.

## 의존성

- Issue #46(응답 envelope) — error 필드 형식 의존. **#46 이후 진행.**

## 마이그레이션/스키마

- DB 변경 없음.

## ADR 여부

- 에러 코드 체계는 대안(HTTP 일반 코드) 대비 도메인별 문자열 enum을 채택한 아키텍처 선택. 향후 영향이 크므로 핸드오프 시 `docs/decisions/` ADR 작성 권고(범위는 사용자 판단).

## 리스크

- 전 서비스 raise 사이트 수정(Medium). 동작(상태코드)은 불변, 응답 본문 구조만 변경.
- 기존 테스트의 에러 응답 단언 갱신 필요.
