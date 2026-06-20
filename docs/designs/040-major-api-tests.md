# 040 Major API Tests

## Scope

프론트엔드 연결 전에 주요 API가 깨지지 않도록 최소 테스트를 보강한다. 프론트 화면과 직접 연결되는 핵심 엔드포인트(관심 종목, 종목 상세, 리서치 요약, 포트폴리오 요약, 알림 후보)와 공통 에러 응답에 대한 테스트가 존재·통과하는지 확인하고, 누락분을 추가한다. 테스트 실행 방법을 문서화한다. 신규 도메인/스키마 변경은 없다.

## Current State

- `tests/`에 다수 API 테스트 존재: `test_watchlists`, `test_assets`, `test_portfolios`, `test_alert_candidates`, `test_alerts`, `test_signals`, `test_theses`, `test_reports`(research), `test_decision_checklist`, `test_research_reports`, `test_error_handlers`, `test_response` 등.
- 공통 테스트 헬퍼: `tests/conftest.py`의 `client`/`db` fixture, `api_data`/`api_meta`/`api_error`, `set_current_user`.

## Coverage Targets

| API | 확인/보강 항목 |
| --- | --- |
| Watchlist | 목록/항목 추가·조회·삭제, 페이지네이션 meta |
| Stock detail | `GET /assets/{id}/detail` 응답 필드 |
| Research summary | `GET /assets/{id}/research-summary` 응답 |
| Portfolio summary | `GET /portfolios/{id}/summary` 응답 |
| Alert candidate | 목록 필터·페이지네이션, read/confirm 상태 전이 |
| Error response | 404/401/422 등 에러 envelope(`{data:null, error:{code}}`) |

## Functions

- 기존 테스트와 중복되지 않게 **공백만 보강**한다. 각 핵심 API의 성공 응답 포맷 + 대표 에러 응답을 최소 1건씩 보장.
- 에러 응답 테스트: 인증 누락(401), 미존재 리소스(404), 잘못된 입력(422)에 대해 공통 envelope 검증(`api_error` 헬퍼 활용).
- 테스트 실행 방법 문서화: `README.md`/`docs/testing.md`에 `uv run pytest`(+ 선택 옵션) 절차 명시.

## Decisions

- 신규 테스트 프레임워크/픽스처 구조를 도입하지 않는다 — 기존 `conftest.py` 패턴(SQLite in-memory, dependency override) 재사용.
- 커버리지 수치 게이트는 이번 범위에서 강제하지 않는다 — 핵심 API 동작·에러 envelope 보장이 목적. 응답 구조 고정(스냅샷)은 #61에서.
- 기존 통과 테스트를 약화/삭제하지 않는다(AGENTS.md 규칙).
