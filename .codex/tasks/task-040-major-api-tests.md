# Codex Handoff Task

## Source Issue

Issue #60 (제목 Issue 40): `[BE] 주요 API 테스트 추가`

## Task Summary

프론트엔드 연결 전에 주요 API가 깨지지 않도록 최소 테스트를 보강한다. 핵심 엔드포인트(관심 종목, 종목 상세, 리서치 요약, 포트폴리오 요약, 알림 후보)와 공통 에러 응답 테스트의 존재·통과를 확인하고 누락분을 추가한다. 테스트 실행 방법을 문서화한다.

## Goal

- 주요 API 테스트가 CI에서 실행된다.
- API 응답 포맷 변경 시 테스트가 실패한다(동작 수준).
- 에러 응답 테스트가 포함된다(401/404/422 공통 envelope).

## Background

- **설계문서 우선**: `docs/designs/040-major-api-tests.md`를 먼저 읽고 따른다.
- 이미 다수 테스트 존재: `tests/test_{watchlists,assets,portfolios,alert_candidates,alerts,signals,theses,reports,decision_checklist,research_reports,error_handlers,response}.py`.
- 공통 헬퍼: `tests/conftest.py`의 `client`/`db` fixture, `api_data`/`api_meta`/`api_error`, `set_current_user`. SQLite in-memory + dependency override 패턴.
- **공백만 보강**한다 — 중복 테스트를 만들지 않는다. 응답 구조 고정(스냅샷)은 #61 범위.

## Implementation Scope

- 핵심 API별 성공 응답 + 대표 에러 응답 최소 1건 보장(공백 보강):
  - Watchlist, Stock detail(`/assets/{id}/detail`), Research summary(`/assets/{id}/research-summary`), Portfolio summary(`/portfolios/{id}/summary`), Alert candidate(목록 + read/confirm).
- 에러 응답 테스트: 인증 누락(401), 미존재 리소스(404), 잘못된 입력(422) 공통 envelope(`{data:null, error:{code}}`) 검증 — `api_error` 활용. 필요 시 `tests/test_error_responses.py`(신규).
- `README.md`/`docs/testing.md` — 테스트 실행 방법 명시(`uv run pytest`).

## Out of Scope

- 응답 schema 스냅샷/contract 고정(= #61).
- 커버리지 수치 게이트 강제.
- 신규 도메인/엔드포인트/스키마.
- 기존 통과 테스트 약화·삭제.

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- 핵심 5개 API 영역의 성공 응답 + 대표 에러 응답이 테스트로 보장됨.
- 에러 envelope(401/404/422)가 공통 포맷으로 검증됨.
- 기존 `conftest.py` 패턴 재사용(신규 픽스처 구조 도입 금지).
- 테스트 실행 방법 문서화.

## Test Requirements

- 위 핵심 API 성공/에러 테스트(공백 보강분).
- 신규/보강 테스트 포함 `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `README.md`/`docs/testing.md` 테스트 실행 안내, `docs/designs/040-major-api-tests.md`.

## ADR Need

불필요 — 테스트 보강.

## Failure Record Need

없음.

## Risk Level

Low — 테스트 추가. 프로덕션 코드 변경 최소.

## Expected Output

- 보강 테스트 + 실행 문서.
- lint/typecheck/pytest 통과. PR body에 `Closes #60`.

## Rules

- 기존 테스트 약화·삭제 금지.
- 중복 테스트 양산 금지(공백만 보강).
- 보호 파일 변경 금지.
- 가정(보강 대상 공백 목록)과 검증 결과 보고.
