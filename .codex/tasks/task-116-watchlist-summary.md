# Codex Handoff Task

## Source Issue

설계: `docs/designs/050-watchlist-summary.md` (Frozen)

## Task Summary

`GET /api/v1/watchlists/{watchlist_id}/summary` 엔드포인트를 신설해 관심 목록 요약(총 종목 수,
위험 증가 종목 수, 최근 추가 종목)을 제공합니다.

## Goal

- `GET /watchlists/{watchlist_id}/summary`가 `WatchlistSummaryResponse`를 반환한다.
- 응답은 `total_count`, `risk_increasing_count`, `recent_items[]`를 포함한다.
- 모든 값은 기존 데이터에서 진실되게 파생되며, 추가 외부 호출은 시세 1회로 제한된다.

## Background — 오케스트레이터가 확정한 사실

- 설계 050이 정본이며 계약은 동결됨. 아래는 그대로 구현할 것.
- `risk_increasing_count` = watchlist 종목 중 **미만료 `RISK_ALERT`** 시그널을 1건 이상 보유한
  **고유 종목 수**(시그널 건수 아님). 미만료 판정은 `SignalRepository._active_clause`를 따른다.
- `recent_items`는 `created_at` 내림차순 상위 `recent_limit`(기본 5)개. 동률은 `id` 내림차순.
  각 항목은 `symbol`, `name`, `created_at`만 노출한다(status 배지 등 판단값 없음).
- 소유권 검증은 기존 `_get_owned_watchlist` 규칙을 재사용한다.
- "추가 리서치 필요", "평균 현금 연관도", 전일 대비 델타, status 배지는 출처가 없어 도입하지 않는다.

## Implementation Scope

- `app/domains/watchlists/schema.py`
  - `RecentWatchlistItemResponse { symbol: str, name: str, created_at: UtcDatetime }` 추가.
  - `WatchlistSummaryResponse { total_count: int, risk_increasing_count: int,
    recent_items: list[RecentWatchlistItemResponse] }` 추가.
- `app/domains/watchlists/service.py`
  - `WatchlistService.get_summary(watchlist_id, user_id, recent_limit=5)` 추가.
  - `total_count`는 `item_repo.count_by_watchlist` 재사용.
  - 최근 종목은 `item_repo.list_by_watchlist(sort="-created_at", limit=recent_limit)`로 얻고
    asset 메타(symbol/name)를 채운다.
- `app/domains/signals/repository.py`
  - `count_assets_with_active_signal(asset_ids, signal_type) -> int` 추가
    (distinct asset_id 수, asset_ids 비면 0).
- `app/api/v1/endpoints/watchlists.py`
  - `GET /{watchlist_id}/summary` 라우트 추가, `success(...)` 반환.

## Out of Scope

- 일별 스냅샷 테이블, 전일 대비 델타.
- status 배지, AI 관찰 메모, 알림 설정.
- 기존 watchlist 엔드포인트/필드/정렬 변경.
- signals 도메인의 쓰기 로직 변경.

## Protected Files

없음.

## Requirements

- 빈 watchlist: `total_count=0`, `risk_increasing_count=0`, `recent_items=[]`.
- asset 가격 표기를 위한 시세 호출은 최대 1회(`list_items_expanded` 패턴). 시세가 불필요하면 호출하지 않음.
- mypy strict 통과(테스트 함수 파라미터 포함 타입 주석 필수).

## Test Requirements

`tests/test_watchlists.py`(또는 해당 파일)에 추가:
- total_count / risk_increasing_count 집계(미만료 RISK_ALERT 보유 종목만 카운트, 만료/다른 타입 제외).
- 동일 종목이 RISK_ALERT 여러 건이어도 1로 카운트(distinct).
- recent_items 정렬(created_at desc, id desc) 및 limit.
- 빈 watchlist 가드.
- 소유권 불일치 시 403/404 (기존 규칙).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q`

## Documentation Impact

- `docs/designs/050-watchlist-summary.md` 추가됨(정본).
- 이 핸드오프 문서 추가.

## ADR Need

불요. 기존 계산값 파생·엔드포인트 추가, 신규 아키텍처 결정 없음.

## Failure Record Need

불요. 국소 변경, 회귀는 테스트로 커버.

## Risk Level

Low. 추가 전용 엔드포인트, 기존 동작 불변.

## Expected Output

- 위 4개 파일 변경 + 테스트 추가.
- 브랜치 `feat/watchlist-summary`에 커밋(한국어 메시지).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
