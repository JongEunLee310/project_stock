# 설계 기록 — 인증 refresh 토큰 확장 (이슈 #96, C3/Q8/N2)

`API 계약 정렬 — 백엔드` 마일스톤. 기존 인증은 **access 토큰만** 발급(`POST /auth/login` → `Token{access_token,
token_type}`). 계약(C3/Q8/N2)에 맞춰 **refresh 토큰 체계**를 도입한다. login 응답에 `refresh_token`·
`expires_in` 추가(계약 변경), `POST /auth/refresh` 신설, 만료 시간 env 설정화(기본 AT 15분 / RT 2일).
FE 인증 흐름(`project_stock_frontend#46`)과 페어.

- 이슈: #96 `[계약정렬] 인증 refresh 토큰 확장 (C3/Q8/N2)`
- 페어: FE `JongEunLee310/project_stock_frontend#46`
- 근거: `docs/api/contract-alignment.md` C3·Q8·N2(§5 Q8 행, 130행 contract 변경 주의)

## 배경 / 현황

- `app/core/security.py`: `create_access_token(subject, expires_delta)`만 존재. JWT claim `{sub, exp}`,
  토큰 **타입 구분 없음**.
- `app/domains/users/schema.py`: `Token{access_token, token_type="bearer"}`.
- `app/domains/users/service.py`: `login`이 `Token(access_token=...)`만 반환.
- `app/api/v1/deps.py`: `get_current_user`가 access 토큰을 디코드(`sub`만 검증).
- `app/core/config.py`: `ACCESS_TOKEN_EXPIRE_MINUTES=30`, refresh 설정 없음. `SECRET_KEY`/`ALGORITHM` 공용.
- `app/api/v1/endpoints/auth.py`: `register`/`login`/`me`. refresh 엔드포인트 없음.
- spec `docs/api/frontend-api-spec.md`(login 196행), contract 테스트 `tests/test_api_contract.py`.

## 핵심 결정

1. **토큰 타입 claim 도입**: access/refresh JWT에 `type`(`"access"`/`"refresh"`) claim 추가. `get_current_user`는
   **`type == "access"`만 허용**(refresh 토큰으로 보호 API 접근 차단). refresh 엔드포인트는 `type ==
   "refresh"`만 허용. `SECRET_KEY`/`ALGORITHM`은 공용 재사용.
2. **만료 env 설정화**(N2): `ACCESS_TOKEN_EXPIRE_MINUTES` 기본 **15**로 변경, `REFRESH_TOKEN_EXPIRE_MINUTES`
   신설(기본 **2880** = 2일). 둘 다 `.env` 오버라이드. `expires_in`(login/refresh 응답)은 **access 만료까지 초**
   = `ACCESS_TOKEN_EXPIRE_MINUTES * 60`.
3. **login 응답 확장**(계약 변경): `Token`에 `refresh_token: str`, `expires_in: int` 추가. `login`이 access +
   refresh 동시 발급. **하위호환**: 기존 필드(`access_token`/`token_type`) 유지 — 추가만.
4. **`POST /auth/refresh` 신설**: 요청 바디 `RefreshRequest{refresh_token}`. 검증 — 디코드 성공 + `type ==
   "refresh"` + 사용자 존재 → 새 access(+ `expires_in`) 발급. 실패(만료/변조/타입 불일치/미존재 사용자) →
   401 `AppException`.
5. **refresh 회전 정책 = 비회전(MVP)**: refresh 시 **access만 갱신**, refresh 토큰은 만료까지 재사용. 응답에
   `refresh_token`은 **포함하지 않음**(FE는 미수신 시 기존 refresh 유지 — FE#46 설계와 정합). 회전(rotation)·
   블랙리스트는 범위 밖 후속.
6. **에러 코드**: refresh 무효/만료는 기존 `ErrorCode.AUTH_INVALID_TOKEN` 재사용(401). 신규 코드 미도입
   (만료/변조 구분이 FE 흐름에 불필요 — 둘 다 재로그인). 자격 불일치는 기존 `AUTH_INVALID_CREDENTIALS`.
7. **Alembic 불필요**: 토큰은 무상태(JWT). User 모델·테이블 변경 없음.

## 모듈 / 시그니처 (스켈레톤)

### `app/core/config.py`

| 변경                                  | 책임                                          |
| ------------------------------------- | --------------------------------------------- |
| `ACCESS_TOKEN_EXPIRE_MINUTES: int = 15` | 기본값 30→15(N2)                            |
| `REFRESH_TOKEN_EXPIRE_MINUTES: int = 2880` | 신설, RT 2일(env)                        |

### `app/core/security.py`

| 심볼                                        | 형태                                          | 책임                                  |
| ------------------------------------------- | --------------------------------------------- | ------------------------------------- |
| `create_access_token(subject, expires_delta?)` | 기존 + claim `type="access"`               | access 발급                           |
| `create_refresh_token(subject, expires_delta?)` | `(str\|int, timedelta?) => str`            | refresh 발급(claim `type="refresh"`, 기본 RT 만료) |
| `decode_token(token)` (선택)                | `(str) => dict`                               | 공통 디코드(JWTError 전파) — 중복 제거용 |

### `app/domains/users/schema.py`

| 심볼                  | 변경                                                | 책임                          |
| --------------------- | --------------------------------------------------- | ----------------------------- |
| `Token`               | `+refresh_token: str`, `+expires_in: int`           | login/refresh 응답(계약)      |
| `RefreshRequest`      | 신규 `{refresh_token: str}`                         | refresh 요청 바디             |

### `app/domains/users/service.py`

| 심볼                          | 형태                          | 책임                                                        |
| ----------------------------- | ----------------------------- | ----------------------------------------------------------- |
| `login(data)`                 | 확장                          | access+refresh 발급, `expires_in` 채워 `Token` 반환         |
| `refresh(refresh_token)`      | `(str) => Token`              | type=refresh 검증·사용자 확인 → 새 access(+`expires_in`). 실패 401 |

### `app/api/v1/endpoints/auth.py`

| 심볼                          | 형태                                         | 책임                          |
| ----------------------------- | -------------------------------------------- | ----------------------------- |
| `refresh(data, db)`           | `POST /refresh` → `ApiResponse[Token]`       | `UserService.refresh` 위임    |

### `app/api/v1/deps.py`

| 변경                          | 책임                                          |
| ----------------------------- | --------------------------------------------- |
| `get_current_user`            | 디코드 후 `type != "access"` 거부(401)        |

## 문서 / 테스트

- `docs/api/frontend-api-spec.md`: login(196행) 응답에 `refresh_token`·`expires_in` 추가, `POST /auth/refresh`
  섹션 신설, 체크리스트(`[ ] POST /api/v1/auth/refresh`) 추가.
- `tests/test_api_contract.py`: login 응답 스키마에 신규 필드, refresh 엔드포인트 계약 케이스 추가.

## 범위 밖

- refresh 토큰 회전·재사용 탐지·블랙리스트(서버 무효화) — 후속.
- 토큰 저장소(Redis 등) 영속화 — JWT 무상태 유지.
- 소셜 로그인·비밀번호 재설정.

## 검증 / 회귀면

- 단위/통합 테스트(`uv run pytest`):
  - login 응답에 `access_token`/`refresh_token`/`expires_in`/`token_type` 포함.
  - `/auth/refresh`: 유효 refresh → 200 + 새 access. 만료/변조/access-토큰-제시/미존재 사용자 → 401.
  - `get_current_user`: **refresh 토큰으로 보호 API 접근 시 401**(type 검증). access 토큰은 정상.
  - 기존 `register`/`login`/`me` 회귀 없음.
- 게이트: `uv run ruff check .` · `uv run mypy app` · `TZ=UTC uv run pytest`. 토큰 `exp`는 UTC 기준
  ([[verify-timezone-tz-utc]]).

## ADR / 실패 기록

- ADR 불요 — 인증 스택(JWT/passlib/jose) 내 확장. 계약은 contract-alignment.md Q8에서 확정.
