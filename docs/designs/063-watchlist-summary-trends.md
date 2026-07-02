# 063 · 관심종목 요약 추이 시계열 (Watchlist Summary Trends)

Status: Draft
작성: Claude Code (orchestrator)
관련: BE #161, FE #96(관심종목 차트 연동), 설계 062(대시보드 추이 시계열 미러)

## 1. 배경

관심종목 상세 화면에서 "현재 보유 종목 수 추이·위험 증가 종목 수 추이"를 차트로 보여주는
수요가 생겼다(BE 이슈 #161). 현재 `GET /watchlists/{watchlist_id}/summary` 엔드포인트는
현재 시점의 요약 카운트(`total_count`, `risk_increasing_count`)만 반환하며 시계열이 없다.

대시보드 추이 시계열(설계 062, BE #155)과 동일한 날짜 윈도우·0채움·시계열 응답 구조를
watchlist 도메인에 이식한다. 서비스·스키마·라우트 패턴은 062를 미러하되, watchlist의
ownership 가드(`_get_owned_watchlist`)와 두 가지 파생 계열(`watchlist_total`·`risk_increasing`)을
적용한다.

**코호트 기준 제약**: `WatchlistItem`은 hard-delete 방식이므로 과거 멤버십 이력이 존재하지
않는다. 따라서 "날짜별 실제 구성"을 재현할 수 없으며, **현재 watchlist 코호트를 고정 기준**으로
각 날짜 D의 as-of 값을 계산하는 방식으로 구현한다. 이 해석("당신의 현재 관심종목 기준
과거 추이")을 배경과 Risks에 명확히 기술한다.

## 2. 범위

포함:

- as-of 추이 계열 2종: 관심종목 총 보유 종목 수·위험 증가 종목 수.
- 응답 스키마 `WatchlistSummaryTrendDataPoint`, `WatchlistSummaryTrendSeries`,
  `WatchlistSummaryTrendResponse`.
- `WatchlistSummaryTrendService` 서비스.
- API 엔드포인트 `GET /watchlists/{watchlist_id}/summary/trends`.
- 테스트: ownership, 계열 단위, API 계약.

비포함(분리):

- FE 변경 — 별도 FE 이슈 #96, 본 BE 머지 후 연동.
- `days` 외 파라미터 추가(예: per-symbol 가격·수익률 추이).
- 기존 `GET /watchlists/{watchlist_id}/summary` 동작 변경 — 현재 요약 카운트 유지.
- 대시보드 추이 변경.
- DB 스키마 변경 — 기존 컬럼 재사용, 신규 테이블·컬럼 없음.
- 캐시 전략 — 필요 시 후속.

## 3. 파생 정의 — 현재 코호트 기준 as-of 추이

`WatchlistItem`이 hard-delete 방식이므로 특정 날짜의 실제 watchlist 구성을 재현할 수 없다.
대신 **현재 watchlist 코호트(현재 보유 항목 전체)**를 고정 기준으로 각 날짜 D의 as-of 값을
계산한다. 이 접근은 "현재 관심종목들이 지난 N일 동안 어떤 추이를 보였는가"를 답하는 것으로,
과거에 삭제된 종목은 추이에 반영되지 않는다.

| 계열 | 정의 | 마지막 날 일관성 |
| --- | --- | --- |
| `watchlist_total` | 현재 watchlist 항목 중 `created_at <= D 끝시각`인 항목 수 | `== total_count` (단조 비감소, D가 today이면 전체 항목) |
| `risk_increasing` | 현재 watchlist 자산(asset_ids) 중 날짜 D 기준 활성 RISK_ALERT 보유 고유 자산 수 | `== risk_increasing_count` |

`risk_increasing` 활성 판정 기준(날짜 D):

- `Signal.created_at <= D 끝시각`
- `Signal.expires_at IS NULL OR Signal.expires_at > D 끝시각`
- `Signal.signal_type == RISK_ALERT`
- `Signal.asset_id IN asset_ids` (현재 watchlist 자산 목록)

0채움: 결측일은 `count = 0`으로 채워 윈도우 전체 날짜를 반환한다. FE가 직접 채울 필요가 없다.

날짜 집계 단위: UTC 캘린더 날짜(YYYY-MM-DD). 062와 동일한 UTC 기준을 따른다.

**Risks**:

- 사용자가 항목을 삭제한 경우 해당 항목의 과거 기여분이 추이에서 사라진다. 현재 soft-delete
  이력이 없으므로 회피할 수 없으며, 이 한계를 API 설명에 노출해야 한다.
- `risk_increasing` 마지막 날과 `risk_increasing_count`의 일관성은 as-of 활성 판정 기준이
  기존 `_active_clause`와 동일한 시각 조건을 사용해야 보장된다. 구현 시 `_active_clause`
  로직을 참고해 동일 조건을 적용한다.

## 4. 응답 스키마

watchlist 도메인에 스키마를 병렬로 정의한다. 대시보드의 `TrendSeries`·`TrendDataPoint`를
재사용하지 않고 `app/domains/watchlists/schema.py`에 독립적으로 선언한다. 도메인 결합을
방지하면서도 와이어 형태는 062와 동일하게 유지해 FE가 대시보드 추이 파서를 재사용할 수
있도록 한다.

`WatchlistSummaryTrendDataPoint(BaseModel)`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| date | str | UTC 캘린더 날짜 (YYYY-MM-DD) |
| count | int | 해당 날 as-of 값 (결측 → 0) |

`WatchlistSummaryTrendSeries(BaseModel)`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| key | str | 계열 식별자: `watchlist_total` / `risk_increasing` |
| data | list[WatchlistSummaryTrendDataPoint] | 날짜 오름차순, 윈도우 전체 (결측일 포함) |

`WatchlistSummaryTrendResponse(BaseModel)`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| days | int | 실제 반환한 윈도우 길이 |
| series | list[WatchlistSummaryTrendSeries] | 계열 목록 (2개 고정) |

API 응답: `ApiResponse[WatchlistSummaryTrendResponse]` — 공통 envelope 준수.

## 5. 서비스

신규 `app/domains/watchlists/trend_service.py`:

```
class WatchlistSummaryTrendService:
    def __init__(self, db: Session) -> None
    def get_trends(self, watchlist_id: int, user_id: int, days: int) -> WatchlistSummaryTrendResponse
```

`get_trends` 책임(순서):

1. `_get_owned_watchlist(watchlist_id, user_id)`로 ownership을 확인한다 — 미존재 404·비소유 403.
   기존 `WatchlistService`의 동일 메서드를 재사용한다.
2. 현재 watchlist 항목 전체에서 `(item.asset_id, item.created_at)` 목록을 얻는다.
3. `days`를 받아 집계 시작일을 계산한다(UTC 기준 `today - days + 1`일). 062 날짜 윈도우 생성
   패턴을 미러한다.
4. 날짜 윈도우를 순회하며 `watchlist_total` as-of 값을 계산한다 — 각 날짜 D에 대해
   `item.created_at <= D 끝시각`인 항목 수.
5. asset_ids를 이용해 날짜 윈도우를 순회하며 `risk_increasing` as-of 값을 계산한다 — 각 날짜
   D에 대해 §3 활성 판정 기준을 적용한 고유 자산 수.
6. 각 계열에 0채움을 적용해 `days`개 날짜 전체를 채운다.
7. `WatchlistSummaryTrendResponse`로 조립해 반환한다.

`risk_increasing` as-of 조회는 기존 `count_assets_with_active_signal`과 달리 날짜 D를 기준
시각으로 받아야 하므로, `SignalRepository`에 날짜 기준 as-of 메서드를 신규 추가하거나 서비스
내에서 날짜 파라미터를 직접 조합한다.

## 6. API

기존 `app/api/v1/endpoints/watchlists.py`에 라우트를 추가한다:

| Method | Path | 쿼리 파라미터 | 응답 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/watchlists/{watchlist_id}/summary/trends` | `days: int` (선택, 기본 14, ge=1, le=90) | `WatchlistSummaryTrendResponse` | 공통 envelope, auth 필요 |

- 인증: `get_current_user` — 기존 watchlist 라우트와 동일한 사용자 컨텍스트.
- `days` 파라미터: `Query(ge=1, le=90, default=14)`, 062와 동일 제약. 범위 초과 시 422.
- ownership: `_get_owned_watchlist` 재사용 — 미존재 404·비소유 403.
- 에러: 빈 watchlist는 404가 아닌 0채움 시계열로 응답한다.

## 7. 의존성

- `app/domains/watchlists/model.py`(`WatchlistItem.created_at`, `WatchlistItem.asset_id`) —
  기존 모델 재사용, 변경 없음.
- `app/domains/signals/model.py`(`Signal.asset_id`, `Signal.signal_type`, `Signal.created_at`,
  `Signal.expires_at`) — 기존 모델 재사용, 변경 없음.
- `app/domains/signals/repository.py`(`SignalRepository`) — as-of 날짜 기준 활성 카운트 메서드
  신규 추가 또는 서비스 내 직접 조합.
- `app/domains/watchlists/service.py`(`_get_owned_watchlist`) — 재사용.
- `app/domains/watchlists/schema.py` — `WatchlistSummaryTrend*` 스키마 추가.
- `app/domains/watchlists/trend_service.py` — 신규.
- `app/api/v1/endpoints/watchlists.py` — 라우트 추가.
- `app/core/response.py`(`ApiResponse`·`success`) — 그대로 사용.

## 8. 테스트

- **Ownership**: watchlist 미존재 시 404, 다른 `user_id` 소유 시 403.
- **`watchlist_total` as-of 누적**: 서로 다른 `created_at`을 가진 항목들에서 날짜 D별 누적
  카운트가 단조 비감소인지, 마지막 날 값이 `total_count`와 일치하는지, 윈도우 시작 이전에
  추가된 항목이 첫날부터 포함되는지 단언.
- **`watchlist_total` 0채움**: 항목 변화가 없는 날의 카운트가 직전 날과 동일(고정)인지,
  빈 watchlist에서 전 구간 0인지 단언.
- **`risk_increasing` 활성 구간**: 만료된 RISK_ALERT는 만료일 이후 카운트에서 제외되고
  활성 구간에는 포함되는지 단언.
- **`risk_increasing` 고유 자산 카운트**: 같은 자산에 복수 RISK_ALERT 신호가 있어도 1로
  집계되는지 단언.
- **`risk_increasing` 마지막 날 일관성**: 마지막 날 값이 현재 `risk_increasing_count`와
  일치하는지 단언.
- **`days` 경계**: `days=1`·`days=90` 경계값에서 정확한 길이의 시계열을 반환하는지,
  `days=0`·`days=91`에서 422를 반환하는지 단언.
- **API 계약**: `GET /watchlists/{watchlist_id}/summary/trends` 응답 envelope 형태, series key
  집합(`watchlist_total`·`risk_increasing`), `days` 필드 일치, 인증 없음 401.

## 9. 비범위 / 후속

- FE 연동 — FE adapter가 `WatchlistSummaryTrendResponse`를 소비, 차트 mock 제거
  (FE 이슈 #96, 본 BE 머지 후 진행).
- soft-delete 도입 — 항목 삭제 이력이 생기면 실제 날짜별 구성 기반 추이로 전환할 수 있다.
  현재는 현재 코호트 고정 방식을 유지한다.
- per-symbol 가격·수익률 추이 — 별도 요구사항으로 다룬다.
- `days` 외 집계 단위(주별·월별) — 본 설계는 일별 고정.
- 캐시 전략 — watchlist가 클 경우 단기 TTL 캐시 도입을 검토한다.
