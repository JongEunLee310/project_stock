# Codex Handoff Task

## Source Issue

Issue #63 (제목 Issue 43): `[BE] Health Check API 개선`

## Task Summary

실행 상태와 의존성 상태를 구분해 확인할 수 있도록 health check를 개선한다. liveness(`/health`)와 readiness(`/health/readiness`)를 분리하고 readiness에서 DB 연결을 확인한다. provider mode·version 표시를 정리한다.

## Goal

- 백엔드 실행 상태를 API로 확인할 수 있다.
- DB 등 주요 의존성 상태를 확인할 수 있다.
- 단순 실행 상태(liveness)와 준비 상태(readiness)를 구분할 수 있다.

## Background

- **설계문서 우선**: `docs/designs/043-health-check-improvement.md`를 먼저 읽고 따른다.
- `/health`가 두 곳에 중복 정의: `app/main.py` 인라인 + `app/api/v1/endpoints/health.py`. 둘 다 `{"status":"ok"}`.
- DB 세션은 `app/db/session.py`, provider mode는 `app/core/config.py`.

## Implementation Scope

- `GET /health`(liveness): 의존성 미점검, 빠른 200. `app/main.py` 중복 제거하고 health 라우터로 일원화.
- `GET /health/readiness`: DB `SELECT 1` 수준 점검(실패 시 503), provider mode·version 포함.
- 응답 포맷 확정(설계문서 기준): `status`, `checks`(db), `providers`, `version`.
- version 단일 소스 선택(pyproject version 또는 build/env arg).

## Out of Scope

- liveness에 의존성 점검 추가(원칙상 분리).
- 외부 모니터링 시스템 연동.
- 로깅 구조(= #62), scheduler(= #64).

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- liveness/readiness가 분리되고 의미가 구분된다.
- readiness가 DB 연결 실패 시 503을 반환한다.
- liveness 응답 포맷 호환 유지(`{"status":"ok"}`).
- `/health` 중복 정의 제거.

## Test Requirements

- liveness 200 테스트.
- readiness 성공/DB 실패(503) 테스트(의존성 모킹 또는 override).
- provider mode·version 포함 검증.
- 전체 `uv run pytest` 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/043-health-check-improvement.md`. 운영/모니터링 안내가 README에 영향 시 갱신(#65에서 통합 정리).

## ADR Need

불필요 — 표준 health 패턴, 아키텍처 결정 없음.

## Failure Record Need

없음.

## Risk Level

Low — 신규 readiness + 중복 제거. liveness 포맷 보존.

## Expected Output

- liveness/readiness 분리 구현 + 테스트.
- lint/typecheck/pytest 통과. PR body에 `Closes #63`.

## Rules

- 스코프 유지. 검증 약화 금지.
- liveness 응답 포맷 호환 유지.
- 보호 파일 변경 금지.
- 가정과 검증 결과 보고.
