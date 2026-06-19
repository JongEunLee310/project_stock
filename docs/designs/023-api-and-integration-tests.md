# Design: API 테스트 보강 및 통합 테스트 (Issue #23)

핵심 API의 회귀 방지 테스트를 정비한다. 현재 도메인별 API 테스트는 다수 존재하나, (1) 인증 경로(register/login/JWT 검증)가 미검증, (2) 테스트 DB 셋업이 파일마다 중복(conftest 부재), (3) 여러 도메인을 HTTP로 가로지르는 end-to-end 통합 테스트 부재, (4) 테스트 실행 방법 미문서화 — 네 가지 갭을 메운다.

## 현황 (기존 테스트 자산)

- 도메인별 API 테스트 존재: assets, watchlists, theses, news(items/raw/analysis), research_reports, alerts, signals, portfolios, job_runs.
- 서비스 계층 통합 테스트 존재: `tests/test_analysis_flow.py` (뉴스→리포트→Signal→Alert 흐름, HTTP 미경유).
- 기존 API 테스트는 `get_current_user`를 dependency override로 우회 → **실제 JWT 인증 경로는 미검증**.
- `conftest.py` 없음 → 각 테스트 파일이 engine/StaticPool/`client`/`override_get_db`/`set_current_user`를 중복 정의.

## 갭과 작업 범위

1. 테스트 DB 설정 중앙화 — 공통 픽스처를 `tests/conftest.py`로 이전.
2. Auth/User API 테스트 신규 — 실제 JWT 발급·검증 경로 검증.
3. HTTP end-to-end 통합 테스트 신규 — 실제 토큰으로 다도메인 연계 검증.
4. 테스트 실행 방법 문서화 — `docs/testing.md` (README 반영은 Issue #25).

## conftest.py (공통 픽스처)

| 항목 | 책임 |
|------|------|
| `engine` / `TestingSessionLocal` | SQLite in-memory + StaticPool 단일 정의 |
| `client` (fixture) | 스키마 생성/드롭, `get_db` override, `TestClient` 제공 |
| `db` (fixture) | 직접 세션 접근이 필요한 테스트용 세션 제공 |
| `set_current_user(user_id, email)` | `get_current_user` override 헬퍼(기존 시그니처 유지) |

- 기존 테스트 파일은 중복 픽스처를 제거하고 conftest 픽스처를 사용하도록 정리한다. **기존 단언/시나리오는 변경하지 않는다.**
- 서비스 계층 테스트(`test_analysis_flow.py`, `test_worker_jobs.py` 등 worker 세션 패치가 필요한 경우)는 별도 픽스처 요구가 있으면 자체 유지 가능.

## Auth/User API 테스트 (`tests/test_auth.py`)

override 없이 실제 인증 경로를 검증한다.

- 회원가입: `POST /api/v1/auth/register` — 201 + UserResponse, 이메일 중복 시 4xx, 잘못된 이메일 형식 422.
- 로그인: `POST /api/v1/auth/login` — 200 + access_token(bearer), 비밀번호 불일치 401, 미존재 사용자 401.
- 본인 조회: `GET /api/v1/auth/me` — 발급 토큰으로 200, 토큰 없음 401, 변조/유효하지 않은 토큰 401.

## 통합 테스트 (`tests/test_integration_flow.py`)

실제 JWT 토큰으로 HTTP를 통해 다도메인 연계를 검증한다(인증 override 미사용).

- 흐름: register → login(토큰 획득) → `Authorization: Bearer` 헤더로 자산 생성 → 관심목록 생성/항목 추가 → 투자 가설 생성 → 포트폴리오 생성/보유 추가 → 포트폴리오 점검(POST /check) → 생성된 Signal을 GET으로 재확인.
- 검증 포인트: 토큰 인증이 실제로 통과하는가, 도메인 간 외래 참조(asset_id 등)가 HTTP 경계에서 일관되는가, 점검이 RISK_ALERT Signal을 생성하고 조회 API로 보이는가.
- 비동기 워커 경유 흐름(뉴스→Alert)은 Redis 의존이므로 이 테스트 범위에서 제외(서비스 계층 `test_analysis_flow.py`가 커버).

## 테스트 실행 문서 (`docs/testing.md`)

- 전체 실행: `uv run pytest`
- 단일 파일/키워드 실행 예시.
- 테스트 DB: SQLite in-memory(외부 의존 없음) 명시.
- lint/typecheck: `uv run ruff check .`, `uv run mypy .`
- README 통합은 Issue #25 범위.

## 범위 외

- 신규 프로덕션 코드/스키마 변경, 엔드포인트 추가.
- Redis/실 워커 구동을 요구하는 비동기 통합 테스트.
- 커버리지 측정 도구 도입(별도 이슈).

## 위험도

Low — 테스트 및 문서 한정. 스키마/보호 파일 변경 없음. Human Gate 불필요.
