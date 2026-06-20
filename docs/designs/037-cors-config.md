# 037 CORS and Frontend Dev Environment Config

## Scope

로컬 프론트엔드 개발 서버와 백엔드가 통신할 수 있도록 CORS 설정을 정리한다. 허용 origin을 환경 변수 기반으로 주입하고(하드코딩 금지), 개발/운영 환경 설정을 분리한다. credentials 사용 여부와 preflight 동작을 정리하고 허용 origin 예시를 문서화한다. 이 작업은 #58(설정 구조)에서 정리한 `Settings`/`APP_ENV` 구조 위에 CORS 항목을 추가한다.

## Current State

- `app/main.py` — `CORSMiddleware` 미적용. CORS 설정 자체가 없다.
- `app/core/config.py` — CORS 관련 항목 없음.

## Config

`app/core/config.py`에 추가(이름 권고):

| Setting | Type | Default | Notes |
| --- | --- | --- | --- |
| `CORS_ORIGINS` | `list[str]` | `[]` | env에서 콤마 구분 문자열 파싱. 개발 기본값은 로컬 프론트(예: `http://localhost:3000`, `http://localhost:5173`) |
| `CORS_ALLOW_CREDENTIALS` | `bool` | `False` | 쿠키/인증 헤더 동반 요청 허용 여부 |

`.env.example`에 `CORS_ORIGINS` 항목과 개발/운영 예시 주석 추가.

## Functions

- `app/main.py` — `app.add_middleware(CORSMiddleware, ...)`를 `settings.CORS_ORIGINS`/`CORS_ALLOW_CREDENTIALS` 기반으로 등록. allow_methods/allow_headers는 합리적 기본값.
- origin 목록은 코드에 하드코딩하지 않고 전적으로 `settings`에서 읽는다.

## Decisions

- origin은 환경 변수로만 주입 — 개발/운영 분리는 각 환경의 `.env`/배포 설정으로 처리, 코드에는 origin 리터럴을 두지 않는다.
- `allow_origins=["*"]`와 `allow_credentials=True`는 동시 사용 불가(스펙 제약) — credentials가 필요하면 명시 origin 목록을 요구. 기본은 credentials off로 시작하고 인증 연동 시 재검토.
- preflight(OPTIONS)는 `CORSMiddleware`가 자동 처리 — 별도 라우트 추가하지 않는다.
- CORS 항목은 #58에서 정리하는 설정 구조를 따른다(중복 정의 금지).

## Implementation Notes

- `CORS_ORIGINS`는 `.env`/프로세스 환경 변수의 콤마 구분 문자열을 `Settings`에서 `list[str]`로 파싱한다.
- `CORS_ALLOW_CREDENTIALS=true`와 `CORS_ORIGINS=*` 조합은 설정 검증에서 거부한다.
- 로컬 개발 origin 예시는 `.env.example`과 프론트엔드 API 문서에만 둔다.
