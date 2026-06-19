# Codex Handoff Task

## Source Issue

Issue #50 (제목 Issue 30): `[BE] 관심 종목 Watchlist API 개선`

## Task Summary

프론트엔드 관심 종목 화면에서 사용할 수 있도록 Watchlist 항목(item)에 관심 사유·태그·메모 필드를 추가하고, 항목 목록 조회 API와 정렬 기준을 제공한다. 중복 등록 방지는 기존 제약을 검증·유지한다.

## Goal

- `WatchlistItem`에 `reason`(관심 사유), `tags`, `memo` 필드가 추가된다.
- 관심 종목 **항목 목록 조회 API**(`GET /api/v1/watchlists/{watchlist_id}/items`)가 추가되고 정렬(`sort`)을 지원한다.
- 항목 추가 API가 사유/태그/메모를 함께 받는다.
- 같은 종목 중복 등록이 방지된다(기존 `uq_watchlist_items_asset` + `WATCHLIST_ITEM_DUPLICATE` 검증 유지·확인).
- 모델 변경에 대한 alembic 마이그레이션이 추가된다.

## Background

- 기존 모델: `app/domains/watchlists/model.py` — `WatchlistItem(watchlist_id, asset_id, priority)` + `UniqueConstraint("watchlist_id","asset_id")`.
- 기존 항목 API: 추가(`POST .../items`)와 삭제(`DELETE .../items/{item_id}`)만 존재하고 **항목 목록 조회 GET이 없다** — 본 태스크에서 추가.
- 중복 방지 에러코드 `WATCHLIST_ITEM_DUPLICATE`는 이미 `app/core/error_codes.py`에 존재하고 서비스에서 사용 중. 신규 코드 추가 불필요.
- 응답은 공통 envelope(`app/core/response.py`의 `success`/`paginated`)를 따른다. 목록은 `meta{page,size,total}`.
- DB는 alembic 사용(`alembic/versions/`). 모델 컬럼 추가 시 마이그레이션 필수.
- 글로벌 설계 원칙: 현재 단계에서 불필요한 추상화 금지. `tags`는 별도 테이블 없이 단순 보관한다.

## Implementation Scope

- `app/domains/watchlists/model.py` — `WatchlistItem`에 컬럼 추가:
  - `reason: str | None`(Text, nullable)
  - `tags`(권고: PostgreSQL JSON 컬럼에 `list[str]`, 기본 `[]`; 단순화를 위해 콤마구분 문자열도 허용 — 택1 후 일관 적용)
  - `memo: str | None`(Text, nullable)
- `app/domains/watchlists/schema.py` — `WatchlistItemCreate`/`WatchlistItemResponse`에 위 3개 필드 반영. 정렬용 enum/Literal(`priority` | `-priority` | `created_at` | `-created_at` 등 최소 집합).
- `app/domains/watchlists/repository.py` — 항목 목록 조회(offset/limit + 정렬), 필드 저장.
- `app/domains/watchlists/service.py` — 항목 목록 조회 + 카운트, 중복 검증 유지, 소유권 검증(`WATCHLIST_FORBIDDEN`/`WATCHLIST_NOT_FOUND`) 재사용.
- `app/api/v1/endpoints/watchlists.py` — `GET /{watchlist_id}/items`(인증 필요, page/size/sort query) 추가. OpenAPI summary/description 포함.
- `alembic/versions/` — 신규 마이그레이션(컬럼 추가).
- `docs/designs/030-watchlist-api-improvement.md` — 스켈레톤 설계문서(필드 표 + 시그니처).

## Out of Scope

- 관심목록(Watchlist) 자체 스키마 변경.
- 시세/공시/분석 데이터 연동(별도 이슈 #51/#52).
- 태그 전용 테이블·태그 마스터·자동완성 등 추가 추상화.
- 기존 추가/삭제 API의 경로·동작 변경(필드 추가만, 하위호환 유지).

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 신규 필드는 모두 optional(추가만으로 기존 데이터/요청이 깨지지 않음).
- 항목 목록 조회는 해당 watchlist 소유자만 가능. 비소유자는 `WATCHLIST_FORBIDDEN`.
- 존재하지 않는 watchlist는 `WATCHLIST_NOT_FOUND`.
- 중복 종목 추가는 `400 WATCHLIST_ITEM_DUPLICATE`(서비스 사전 검증 + DB IntegrityError 양쪽 방어 유지).
- 정렬 파라미터는 화이트리스트(허용 값 외 입력은 `422 VALIDATION_ERROR`).
- 마이그레이션은 upgrade/downgrade 모두 작성.

## Test Requirements

- 항목에 사유/태그/메모를 포함해 추가·조회가 왕복되는 테스트.
- 중복 추가 시 `WATCHLIST_ITEM_DUPLICATE` 반환 테스트.
- 정렬 파라미터별 순서 검증 + 잘못된 정렬값 `422`.
- 소유권 위반(`WATCHLIST_FORBIDDEN`) 테스트.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/030-watchlist-api-improvement.md` 신규(스켈레톤).
- `docs/api/frontend-api-spec.md`의 관심종목 섹션에 신규 GET items + 확장 필드 반영(라우트 체크리스트 포함).

## ADR Need

없음 — 기존 도메인의 필드/조회 확장. 아키텍처 변경 아님.

## Failure Record Need

없음(구현 중 회귀·정책 충돌 발생 시에만 기록).

## Risk Level

Low~Medium — DB 마이그레이션 동반. 스키마는 additive라 회귀 위험 낮음.

## Expected Output

- 모델/스키마/서비스/엔드포인트 + 마이그레이션 + 테스트.
- `uv run pytest` 통과, lint/typecheck 통과.
- PR body에 `Closes #50`.

## Rules

- 스코프 내에서만 작업. 다른 도메인 변경 금지.
- 검증을 약화하지 않는다(중복 방지·정렬 화이트리스트 유지).
- 보호 파일 변경 금지.
- 가정과 검증 결과를 PR에 보고.
