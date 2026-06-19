# Codex Handoff Task

## Source Issue

Issue #46 (제목 Issue 26): `[BE] 공통 API 응답 포맷 정리`

## Task Summary

모든 API 응답을 단일 envelope `{data, message, error, meta}`로 통일한다. 성공/목록 응답을 위한 `app/core/response.py`를 신규 작성하고, v0.1의 전 엔드포인트(~30개)를 envelope로 소급 적용한다. 목록 엔드포인트에 `page`/`size` 페이지네이션을 도입한다. 에러 envelope 본문은 본 태스크에서 구조만 자리잡고, 코드 체계·핸들러는 Issue #47에서 채운다.

## Goal

- `ApiResponse[T]`, `PageMeta`, `success()`, `paginated()`가 `app/core/response.py`에 존재한다.
- 모든 적용 대상 엔드포인트가 `ApiResponse[...]`를 반환하고 OpenAPI 스키마에 envelope가 반영된다.
- 목록 엔드포인트가 `page`/`size`를 받고 `meta`에 page/size/total을 채운다.
- 기존 API 테스트가 envelope 기준으로 갱신되어 전부 통과한다.

## Background

- 설계 문서: `docs/designs/026-common-response-format.md`
- 현재 엔드포인트는 모델/`list[모델]`을 그대로 반환(envelope 없음). 라우터 목록은 `app/api/v1/router.py`, 엔드포인트는 `app/api/v1/endpoints/*.py`.
- 프론트엔드 미착수 상태 → 응답 계약 파기 허용(이슈 본문이 "기존 API 응답 구조 수정"을 명시).
- 에러 응답(`error` 필드 채움)과 예외 핸들러는 Issue #47 범위. 본 태스크에서는 `error`/`message` 필드를 envelope에 정의만 하고 성공 경로만 구현한다.

## Implementation Scope

- `app/core/response.py` (신규) — `ApiResponse[T]`(Generic Pydantic v2), `PageMeta`, `success()`, `paginated()`.
- `app/api/v1/endpoints/*.py` — 설계 문서 적용 대상 표의 엔드포인트 `response_model` 교체 + 반환 래핑. 목록 엔드포인트에 `page`(기본1, ≥1)/`size`(기본20, 1~100) 쿼리 추가.
- 목록 total 계산을 위해 필요한 repository/service에 count 또는 (items,total) 반환 추가(최소 변경).
- 기존 테스트 파일 — 응답 단언을 envelope 기준으로 갱신.

## Out of Scope

- 에러 코드 enum, 예외 핸들러, raise 사이트 수정 (Issue #47).
- 정렬/필터 공통 규약 (Issue #36) — 본 태스크는 page/size만.
- `/health`, `/api/v1/health` envelope 적용 (외부 헬스체크 호환 위해 제외).
- DB 스키마 변경.
- 신규 도메인/엔드포인트 추가.

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- `ApiResponse[T]`: `data: T | None`, `message: str | None`, `error: dict | None`, `meta: PageMeta | None`. 모든 필드 기본 None.
- `success(data, message=None)` → data 채운 envelope. `paginated(items, page, size, total)` → data=items, meta=PageMeta.
- 단건 성공은 `success(...)`, 목록은 `paginated(...)` 사용.
- 204 응답(포지션/관심항목 삭제 등)은 200 + `success(None)`로 통일.
- 목록 엔드포인트: `page`/`size` 유효성은 FastAPI Query 제약(ge/le)으로. 범위 밖은 422.
- `/health` 계열은 변경하지 않는다.

## Test Requirements

- 신규 `tests/test_response.py`(또는 적절 위치)로 `success`/`paginated` 단위 검증.
- 기존 API 테스트의 응답 접근을 envelope 기준(`body["data"]`, `body["meta"]`)으로 갱신. **케이스 수·단언 강도 약화 금지.**
- 목록 엔드포인트 테스트에 page/size + meta.total 검증 추가.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/026-common-response-format.md` 작성됨(변경 불필요).
- README의 API 예시가 있으면 envelope 반영 여부 확인(있을 때만).

## ADR Need

없음 — envelope 형식은 설계 문서로 충분. (에러 코드 체계 ADR은 #47에서 판단.)

## Failure Record Need

없음.

## Risk Level

Medium — 전 엔드포인트 응답 계약 변경(표면적 넓음). DB·동작(상태코드)은 불변. 프론트 미착수로 호환성 파기 허용. Human Gate 불필요.

## Expected Output

- `app/core/response.py` 신규 + 전 적용 대상 엔드포인트 래핑.
- 기존/신규 테스트 통과, lint/typecheck 통과.
- PR body에 `Closes #46`.

## Rules

- 스코프 외(에러 핸들러/코드, /health) 변경 금지.
- 기존 테스트 약화 금지.
- 보호 파일 변경 금지.
- 가정과 검증 결과 보고.
