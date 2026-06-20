# Codex Handoff Task

## Source Issue

Issue #61 (제목 Issue 41): `[BE] API Contract Snapshot 테스트 추가`

## Task Summary

프론트엔드와 약속한 응답 구조가 의도치 않게 바뀌지 않도록 contract(스냅샷) 테스트를 추가한다. 주요 API 응답 schema(필수 필드·타입)를 고정하고, 누락/타입 변경을 감지한다. OpenAPI schema를 확인하고 contract 변경 검토 기준·프론트 영향 범위 확인 절차를 문서화한다.

## Goal

- 주요 API의 응답 구조가 테스트로 보호된다.
- 필수 필드 누락 시 테스트가 실패한다.
- API contract 변경 시 검토 기준이 문서화된다.

## Background

- **설계문서 우선**: `docs/designs/041-api-contract-snapshot-tests.md`를 먼저 읽고 따른다.
- **선행 의존성**: #60(`task-040`)이 핵심 API 동작 테스트를 보강한 뒤, 본 작업이 응답 **구조**를 고정한다. #56(`task-036`)의 query 규칙 정리 이후 응답이 안정화된 상태를 전제.
- 응답 envelope: `app/core/response.py`의 `ApiResponse{data,message,error,meta}`, `PageMeta{page,size,total}`.
- FastAPI가 `/openapi.json`(`app.openapi()`) 자동 제공.
- 테스트 헬퍼: `tests/conftest.py`(`client`, `api_data`, `api_meta`, `api_error`).

## Implementation Scope

- `tests/test_api_contract.py`(신규) — 프론트 직접 연동 API(watchlist, stock detail, research summary, portfolio summary, alert candidate 목록)의 응답 data 필수 키·타입을 고정. 명시적 키/타입 단언 또는 expected schema dict 비교.
- OpenAPI 확인 테스트 — `app.openapi()`에서 핵심 경로·응답 컴포넌트 존재 검증.
- `docs/api/frontend-api-spec.md` — "Contract 변경 검토 기준"과 "프론트 영향 범위 확인 절차" 절 추가.
- `docs/designs/041-api-contract-snapshot-tests.md` — 달라지면 갱신.

## Out of Scope

- 응답 값(데이터 내용) 고정 — 구조만 고정.
- 외부 스냅샷 라이브러리 도입(기본은 명시 단언; 도입 시 사유 명시).
- 신규 도메인/엔드포인트/스키마.

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- 주요 API 응답의 필수 필드·타입이 테스트로 고정됨.
- 필수 필드 누락/타입 변경 시 테스트 실패.
- OpenAPI에서 핵심 경로 존재 확인.
- contract 변경 검토 기준·프론트 영향 범위 절차 문서화.

## Test Requirements

- 핵심 API 응답 구조 contract 테스트(필수 키·타입).
- 필수 필드 누락 감지(역케이스) 테스트.
- OpenAPI 경로/스키마 존재 테스트.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/api/frontend-api-spec.md`(검토 기준·영향 절차), `docs/designs/041-api-contract-snapshot-tests.md`.

## ADR Need

불필요 — 테스트/문서 추가. 외부 스냅샷 라이브러리를 도입한다면 의존성 추가 사유를 PR에 명시(필요 시 ADR 검토).

## Failure Record Need

없음.

## Risk Level

Low — 테스트/문서 추가. 프로덕션 코드 변경 없음.

## Expected Output

- `tests/test_api_contract.py` + OpenAPI 테스트 + 문서.
- lint/typecheck/pytest 통과. PR body에 `Closes #61`.

## Rules

- 응답 구조만 고정(값 고정 금지).
- 외부 라이브러리 도입은 최소화·사유 명시.
- 보호 파일 변경 금지.
- 가정(고정 대상 API, 라이브러리 사용 여부)과 검증 결과 보고.
