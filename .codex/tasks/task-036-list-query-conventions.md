# Codex Handoff Task

## Source Issue

Issue #56 (제목 Issue 36): `[BE] 페이지네이션, 정렬, 필터링 공통 규칙 추가`

## Task Summary

목록형 API의 페이지네이션·정렬·필터링 query parameter 규칙을 공통화한다. 현재 각 엔드포인트가 `page`/`size`를 중복 선언하고 정렬/필터가 흩어져 있다. 공유 의존성과 합의된 규칙으로 정리하고, 관심 종목·알림 후보 목록에 적용한다.

## Goal

- 목록 API가 동일한 query parameter 규칙(`page`/`size`/`sort`)을 따른다.
- 응답에 pagination meta(`page`, `size`, `total`)가 포함된다(기존 `PageMeta` 유지).
- 정렬 규칙(`field`/`-field`, 허용 필드 allowlist)이 정의되고 검증된다.
- 프론트 테이블/리스트와 연결하기 쉬운 일관된 구조가 된다.

## Background

- **설계문서 우선**: `docs/designs/036-list-query-conventions.md`를 먼저 읽고 그 규칙/함수/Decisions를 따른다. 구현 중 달라지면 설계문서를 함께 갱신한다.
- 이미 존재: `app/core/response.py`의 `PageMeta(page,size,total)`, `paginated(...)` — 재정의 금지, 그대로 사용.
- 중복 현황: `watchlists`, `portfolios`, `alerts`, `assets`, `signals`, `job_runs`, `alert_candidates` 엔드포인트가 `page: Query(ge=1)=1`, `size: Query(ge=1,le=100)=20`를 각자 반복.
- 정렬은 현재 `watchlists` items의 `WatchlistItemSort` Literal만 존재.
- 응답 포맷/동작은 바꾸지 않는다 — 중복 제거 + 규칙 명문화가 목적. contract 보호는 #61 범위.

## Implementation Scope

- `app/core/pagination.py`(신규) — `PaginationParams` FastAPI 의존성(`page`/`size` Query 통합, `offset`/`limit` 제공). 정렬 파싱 헬퍼(`sort` 문자열 → `(field, direction)`, 허용 필드 검증).
- 적용(필수): `app/api/v1/endpoints/watchlists.py`, `app/api/v1/endpoints/alert_candidates.py` — 공유 의존성으로 교체, 정렬 규칙 적용.
- 적용(점진, 동작 불변): 나머지 목록 엔드포인트의 `page`/`size` 중복을 `PaginationParams` 의존성으로 교체.
- `docs/designs/036-list-query-conventions.md` — 구현과 달라지면 갱신.
- `docs/api/frontend-api-spec.md` — 공통 query 규칙(페이지네이션/정렬/필터) 절 추가 또는 갱신.

## Out of Scope

- cursor 기반 페이지네이션 도입.
- 다중 정렬·generic 필터 파서.
- 응답 envelope/`PageMeta` 구조 변경.
- 신규 도메인/테이블/마이그레이션.

## Protected Files

변경하지 않는다: `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`, `docs/harness/`, `docs/decisions/`.

## Requirements

- 공유 `PaginationParams` 의존성 도입, `page`(≥1, 기본1)/`size`(1..100, 기본20) 규칙 통일.
- 정렬 `sort`: `field` 오름/`-field` 내림, 엔드포인트별 허용 필드 미준수 시 422.
- 필터는 리소스별 명시적 typed param 유지(generic 금지).
- watchlist/alert candidate 목록에 규칙 적용, meta 포함.
- 기존 응답 포맷·동작 불변.

## Test Requirements

- `PaginationParams` 기본값/경계값(size 상한 100, page 하한 1) 테스트.
- 정렬 파싱: 허용 필드 오름/내림, 미허용 필드 422 테스트.
- watchlist/alert candidate 목록 페이지네이션 meta 테스트(기존 테스트 유지·보강).
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/036-list-query-conventions.md` 참고/갱신.
- `docs/api/frontend-api-spec.md`에 공통 query 규칙 명시.

## ADR Need

불필요 — 기존 구조 내 공통화. 응답 포맷/아키텍처 변경 없음.

## Failure Record Need

없음.

## Risk Level

Low — 동작 불변 리팩터링 + 정렬 규칙 추가. 다수 엔드포인트 touch하므로 회귀 테스트로 보호.

## Expected Output

- `app/core/pagination.py` + 적용 엔드포인트 + 테스트.
- lint/typecheck/pytest 통과. PR body에 `Closes #56`.

## Rules

- 응답 포맷/동작을 바꾸지 않는다(중복 제거·규칙화만).
- 기존 테스트 약화·삭제 금지.
- 보호 파일 변경 금지.
- 가정(정렬 허용 필드 집합, 점진 적용 범위)과 검증 결과 보고.
