# 036 List Query Conventions (Pagination / Sorting / Filtering)

## Scope

목록형 API가 공통의 페이지네이션·정렬·필터링 query parameter 규칙을 따르도록 공통화한다. 현재 각 엔드포인트가 `page`/`size` Query 파라미터를 개별 선언(중복)하고, 정렬은 엔드포인트별 임시 Literal(`WatchlistItemSort`), 필터는 엔드포인트별 개별 파라미터로 흩어져 있다. 이를 공유 의존성과 합의된 규칙으로 정리하고, 관심 종목·알림 후보 목록에 적용한다. 리서치 이력 목록 등 후속 목록 API도 동일 규칙을 재사용할 수 있는 구조로 만든다.

응답 envelope(`ApiResponse`/`PageMeta`)와 `paginated` 헬퍼는 이미 존재하므로 재정의하지 않고 그대로 사용한다. 신규 도메인/테이블은 없다.

## Current State

- `app/core/response.py` — `PageMeta(page, size, total)`, `paginated(items, page, size, total)` 이미 존재.
- 목록 엔드포인트(`watchlists`, `portfolios`, `alerts`, `assets`, `signals`, `job_runs`, `alert_candidates`)가 `page: Query(ge=1)=1`, `size: Query(ge=1, le=100)=20`를 **각자 반복 선언**.
- 정렬: `watchlists` items만 `sort: WatchlistItemSort` Literal 사용. 통일 규칙 없음.
- 필터: 엔드포인트별 개별 Query(예: assets `is_active`, alert_candidates `candidate_type`/`importance`/`status`). 통일된 명명/검증 규칙 없음.

## Query Parameter Rules

| 구분 | 규칙 | 비고 |
| --- | --- | --- |
| 페이지네이션 | `page`(int, ≥1, 기본 1), `size`(int, 1..100, 기본 20) | 응답 `meta = {page, size, total}` |
| 정렬 | `sort`(str, 선택). `field` 오름차순 / `-field` 내림차순. 엔드포인트별 허용 필드 allowlist 검증, 미허용 시 422 | 단일 필드(MVP). 다중 정렬은 범위 외 |
| 필터링 | 리소스별 명시적 typed query param(generic 필터 금지). enum 값은 Enum 타입으로 검증, 미지정 시 전체 | 기존 패턴 유지·정리 |

## Functions

- `app/core/pagination.py`(신규) — `PaginationParams`(FastAPI 의존성). `page`/`size` Query 선언을 단일 의존성으로 통합, `offset`/`limit` 계산 책임. 각 목록 엔드포인트는 `Depends(PaginationParams)`로 교체.
- `SortParam` 헬퍼(또는 엔드포인트별 sort 의존성 팩토리) — 허용 필드 집합을 받아 `sort` 문자열을 `(field, direction)`로 파싱·검증. 미허용 필드는 validation error.
- 적용 대상: `app/api/v1/endpoints/watchlists.py`(목록 + items), `app/api/v1/endpoints/alert_candidates.py`. 그 외 목록 엔드포인트는 `PaginationParams` 의존성으로 점진 정리(동작 변경 없이 중복 제거).
- 정렬 허용 필드: watchlist items는 기존 동작과 같은 `priority`, `created_at`을 허용한다. alert candidates는 기존 기본 정렬 `-created_at`을 유지하고 안정적인 `created_at`, `id`만 허용한다.

## Decisions

- 응답 메타 구조(`page/size/total`)는 기존 `PageMeta` 유지 — 프론트 연동 호환성. cursor 기반 페이지네이션은 도입하지 않는다(MVP는 offset/page).
- 정렬은 `-` 접두 단일 필드 규칙으로 최소화 — 다중 정렬/임의 표현식은 과한 복잡도라 범위 외.
- 필터는 generic query 파서를 만들지 않고 리소스별 명시 파라미터를 유지한다 — 타입 안정성과 OpenAPI 문서화 이점.
- 기존 동작/응답 포맷은 바꾸지 않는다 — 중복 제거와 규칙 명문화가 목적. contract 보호는 #61에서.
