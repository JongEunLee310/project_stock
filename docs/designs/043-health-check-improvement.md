# 043 Health Check API Improvement

## Scope

백엔드 실행 상태와 의존성 상태를 구분해 확인할 수 있도록 health check를 개선한다. liveness(`/health`)와 readiness(`/health/readiness`)를 분리하고, readiness에서 DB 연결 상태를 확인한다. provider mode·build/version 표시 여부를 정리하고 응답 포맷을 확정한다.

## Current State

- `/health`가 두 곳에 중복 정의: `app/main.py` 인라인 + `app/api/v1/endpoints/health.py`. 둘 다 `{"status": "ok"}` 반환.
- DB/Redis 등 의존성 상태 확인 없음. version/provider 정보 없음.

## Structure

| 엔드포인트 | 책임 |
| --- | --- |
| `GET /health` | liveness — 프로세스가 살아있음만 확인. 의존성 미점검, 빠른 200. |
| `GET /health/readiness` | readiness — DB 연결 점검(실패 시 503). provider mode·version 포함. |

## Response Format

- liveness: `{"status": "ok"}` (envelope 미적용, 모니터링 호환 유지).
- readiness: `status`, `checks`(예: `db`), `providers`(mode), `version`을 포함. 정확한 키/envelope 적용 여부는 구현 시 확정.

## Functions (시그니처 + 책임)

- readiness 핸들러: DB 세션으로 `SELECT 1` 수준 점검 + provider mode(`settings`) + version 조합.
- `app/main.py`의 중복 `/health` 제거 — health 라우터로 일원화.

## Decisions

- liveness는 의존성을 점검하지 않는다(orchestration의 liveness/readiness 구분 원칙).
- version 소스는 단일 소스로 선택한다(pyproject version 또는 build/env arg).
- Redis는 worker 의존성 — readiness 포함 여부 및 실패를 hard fail(503)/degraded 중 어느 것으로 둘지 구현 시 결정.
- 응답 envelope/스키마 변경으로 기존 모니터링 호환을 깨지 않는다(liveness 포맷 유지).
