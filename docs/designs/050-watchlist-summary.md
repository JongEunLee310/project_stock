# 050 · Watchlist Summary 엔드포인트

Status: Frozen
Track: BE
Pair: FE 71 (`docs/designs/71-watchlist-summary-wiring.md`)

## 1. 배경

WatchlistPage 상단 요약 카드와 "새로 추가된 관심 종목" 목록이 mock(`mockWatchlistSummary`,
`mockRecentWatchlist`)으로 남아 있습니다. BE가 진실되게 계산 가능한 값만 노출하는 기존 원칙
([[049-portfolio-risk-exposures]] 선례)에 따라, 기존 데이터에서 파생 가능한 항목만 요약 엔드포인트로
제공합니다.

## 2. 범위

### 포함 (진실 계산 가능)

- `total_count` — 관심 목록 종목 수 (`count_items` 재사용).
- `risk_increasing_count` — 관심 목록 종목 중 미만료 `RISK_ALERT` 시그널을 보유한 종목 수.
- `recent_items[]` — 최근 추가된 종목 목록 (`created_at` 내림차순 상위 N개, asset 정보 포함).

### 제외 (출처 없음 / 별도 트랙)

- "추가 리서치 필요", "평균 현금 연관도" 카드 — 판단 출처가 없어 도입하지 않습니다.
- 모든 카드의 "전일 대비" 델타 — 일별 스냅샷 테이블이 없어 산출 불가. 스냅샷은 별도 결정 사항.
- 최근 추가 종목의 status 배지(안정/관망) — 판단값 출처 없음.
- AI 관찰 메모, 빠른 알림 설정 — 정성 AI / alerts 계약 트랙.

## 3. 계약

### 3.1 엔드포인트

```
GET /api/v1/watchlists/{watchlist_id}/summary
```

- 인증: `get_current_user`. 소유권 검증은 기존 `_get_owned_watchlist` 규칙을 따릅니다.
- 응답: `ApiResponse[WatchlistSummaryResponse]` (`success(...)`).
- 외부 호출: `recent_items`의 asset 가격 표기를 위해 `get_quote`를 최대 1회 호출합니다
  (`list_items_expanded`와 동일 패턴). 시세가 불필요하면 호출하지 않습니다.

### 3.2 스키마 (`app/domains/watchlists/schema.py`)

`RecentWatchlistItemResponse(BaseModel)`
- `symbol: str`
- `name: str`
- `created_at: UtcDatetime`

`WatchlistSummaryResponse(BaseModel)`
- `total_count: int`
- `risk_increasing_count: int`
- `recent_items: list[RecentWatchlistItemResponse]`

### 3.3 서비스 (`app/domains/watchlists/service.py`)

`WatchlistService.get_summary(watchlist_id, user_id, recent_limit=5) -> WatchlistSummaryResponse`
- 책임: 소유권 검증 → 종목 수 집계 → 위험 증가 종목 수 집계 → 최근 추가 종목 N개 구성 → 응답 조립.
- `total_count`는 `item_repo.count_by_watchlist`를 재사용합니다.
- `risk_increasing_count`는 watchlist의 asset_id 집합에 대해 미만료 `RISK_ALERT` 보유 종목 수를
  signals repository에서 조회합니다(아래 3.4).
- `recent_items`는 `item_repo.list_by_watchlist(sort="-created_at", limit=recent_limit)`로 얻고,
  asset 메타(symbol/name)를 채웁니다. 빈 목록이면 `[]`.

### 3.4 signals repository 읽기 메서드 (`app/domains/signals/repository.py`)

`SignalRepository.count_assets_with_active_signal(asset_ids, signal_type) -> int`
- 책임: 주어진 asset_id 집합 중 미만료(`_active_clause`) 시그널을 1건 이상 보유한 **고유 종목 수**를
  반환합니다(시그널 건수가 아니라 distinct asset_id 수).
- `asset_ids`가 비면 0.

## 4. 결정·가드

- watchlist에 종목이 없으면 `total_count=0`, `risk_increasing_count=0`, `recent_items=[]`.
- `recent_items` 정렬은 `created_at` 내림차순, 동률은 `id` 내림차순으로 결정적.
- 기존 watchlist 엔드포인트·필드·정렬은 변경하지 않습니다(추가만).

## 5. 범위 밖

- 일별 스냅샷 테이블 및 전일 대비 델타.
- status 배지, AI 관찰 메모, 알림 설정.
- 의미 분류(테마/성장주 등) 하드코딩.
