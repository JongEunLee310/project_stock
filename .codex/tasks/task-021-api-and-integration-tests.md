# Codex Handoff Task

## Source Issue

Issue #23: API 테스트 작성

## Task Summary

핵심 API 회귀 테스트를 정비한다. 테스트 DB 셋업을 `conftest.py`로 중앙화하고, 미검증 상태인 Auth/User API 테스트와 HTTP end-to-end 통합 테스트를 신규 작성하며, 테스트 실행 방법을 문서화한다. 기존 도메인별 API 테스트는 대부분 존재하므로 갭만 메운다.

## Goal

- 공통 테스트 픽스처(engine/StaticPool/`client`/`db`/`set_current_user`)를 `tests/conftest.py`로 단일화한다.
- 기존 API 테스트 파일의 중복 픽스처를 제거하고 conftest를 사용하도록 정리한다(단언·시나리오 불변).
- 실제 JWT 인증 경로(register/login/me)를 검증하는 Auth/User API 테스트를 추가한다.
- 실제 토큰으로 다도메인을 가로지르는 HTTP 통합 테스트를 추가한다.
- 테스트 실행 방법을 `docs/testing.md`로 문서화한다.

## Background

- 설계 문서: `docs/designs/023-api-and-integration-tests.md`
- 기존 API 테스트는 `app.api.v1.deps.get_current_user`를 override해 **실제 JWT 검증 경로를 우회**한다. 신규 Auth/통합 테스트는 override 없이 실제 토큰 경로를 검증한다.
- 인증: `POST /api/v1/auth/register`(201), `POST /api/v1/auth/login`(Token), `GET /api/v1/auth/me`(Bearer). 토큰은 `app/api/v1/deps.py`에서 SECRET_KEY/ALGORITHM으로 JWT 디코드.
- 테스트 DB: SQLite in-memory + StaticPool, `get_db` override (기존 패턴 그대로).
- 포트폴리오 점검 `POST /api/v1/portfolios/{id}/check`는 동기적으로 RISK_ALERT Signal을 생성 → 통합 테스트의 Signal 생성 검증에 사용.
- 비동기 워커(뉴스→Alert)는 Redis 의존이므로 통합 테스트 범위에서 제외(서비스 계층 `tests/test_analysis_flow.py`가 커버).

## Implementation Scope

- `tests/conftest.py` (신규) — 공통 `engine`/`TestingSessionLocal`/`client`/`db` 픽스처 + `set_current_user` 헬퍼.
- 기존 테스트 파일 정리 — 중복 픽스처/엔진 정의 제거 후 conftest 사용. 대상 예: `test_assets.py`, `test_watchlists.py`, `test_theses.py`, `test_alerts.py`, `test_research_reports.py`, `test_signals.py`, `test_portfolios.py`, `test_news_items.py`, `test_raw_news.py`, `test_job_runs.py` 등 `client`/`set_current_user`를 자체 정의한 파일.
- `tests/test_auth.py` (신규) — Auth/User API 테스트.
- `tests/test_integration_flow.py` (신규) — HTTP end-to-end 통합 테스트.
- `docs/testing.md` (신규) — 테스트 실행 방법 문서.

## Out of Scope

- 프로덕션 코드/스키마/엔드포인트 변경 (테스트가 기존 동작을 드러내야 함. 버그 발견 시 수정하지 말고 보고).
- Redis/실 워커 구동이 필요한 비동기 통합 테스트.
- 서비스 계층 테스트(`test_analysis_flow.py`, `test_worker_jobs.py`)의 자체 픽스처를 무리하게 conftest로 통합 (worker 세션 패치 등 특수 요구가 있으면 자체 유지).
- 커버리지 측정 도구 도입.
- README 반영 (Issue #25 범위).

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`
- `docs/decisions/`

## Requirements

### conftest 중앙화
- `tests/conftest.py`에 `engine`(sqlite in-memory + StaticPool), `TestingSessionLocal`, `client` 픽스처(스키마 create/drop + `get_db` override + `TestClient`), `db` 픽스처(직접 세션), `set_current_user(user_id, email)` 헬퍼를 정의.
- 기존 테스트 파일은 동일 이름 픽스처/헬퍼 중복 정의를 제거하고 conftest 것을 사용. **기존 테스트의 단언·케이스 수를 줄이거나 약화하지 않는다.**

### Auth/User API 테스트 (override 미사용)
- register: 201 + UserResponse(email, is_active), 이메일 중복 4xx, 잘못된 이메일 형식 422.
- login: 200 + `access_token`/`token_type=bearer`, 비밀번호 불일치 401, 미존재 사용자 401.
- me: 발급 토큰으로 200(본인 email 반환), Authorization 헤더 없음 401, 변조 토큰 401.

### 통합 테스트 (override 미사용, 실제 토큰)
- register → login으로 받은 토큰을 `Authorization: Bearer <token>` 헤더로 사용.
- 자산 생성 → 관심목록 생성/항목 추가 → 투자 가설 생성 → 포트폴리오 생성/보유 추가 → `POST /portfolios/{id}/check` → 응답 또는 Signal 조회 API로 RISK_ALERT Signal 생성 확인.
- 각 단계 status code와 도메인 간 id 연계(asset_id 등) 일관성 검증.

### 문서
- `docs/testing.md`: 전체 실행(`uv run pytest`), 단일 파일/키워드 실행 예시, 테스트 DB(SQLite in-memory, 외부 의존 없음) 설명, lint/typecheck 명령.

## Test Requirements

- 신규 테스트 포함 `uv run pytest` 전체 통과.
- 기존 테스트 전부 통과 유지(개수 감소·약화 금지).
- 신규 Auth/통합 테스트는 `get_current_user` override를 사용하지 않는다.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/023-api-and-integration-tests.md` 이미 작성됨 (변경 불필요).
- `docs/testing.md` 신규 작성. README 반영은 Issue #25.

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Low — 테스트 및 문서 한정. 스키마·프로덕션 코드·보호 파일 변경 없음. Human Gate 불필요. conftest 적용을 위한 기존 테스트 파일 정리만 수반(단언 불변).

## Expected Output

- 위 scope 파일 신규 작성 및 기존 테스트 파일 정리.
- `uv run pytest` 전체 통과(신규 케이스 포함), lint/typecheck 통과.
- PR body에 closing keyword 포함 (`Closes #23`).

## Rules

- 스코프 외(프로덕션 코드) 변경 금지. 버그 발견 시 수정 말고 보고.
- 기존 테스트 약화 금지.
- 보호 파일 변경 금지.
- 가정과 검증 결과를 보고.
