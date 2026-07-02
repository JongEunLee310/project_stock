# Codex Handoff Task

## Source Issue

BE #161(관심종목 요약 추이 시계열 endpoint). 설계 `docs/designs/063-watchlist-summary-trends.md`.
FE #96(관심종목 요약 스파크라인 실데이터)의 BE 선행. 대시보드 추이(설계 062,
`app/domains/dashboard/trend_service.py`)를 직접 미러한다.

## Task Summary

`GET /api/v1/watchlists/{watchlist_id}/summary/trends?days=14`를 신설한다. 대시보드 추이와
동일한 날짜 윈도우·0채움·응답 와이어 형태를 watchlist 도메인에 이식하되, ownership 가드와
두 파생 계열(`watchlist_total`·`risk_increasing`)을 **현재 watchlist 코호트 기준 as-of**로
계산한다.

## Goal

완료 시 참이어야 할 것:

- `GET /watchlists/{watchlist_id}/summary/trends`가 auth·ownership(미존재 404·비소유 403)을
  적용하고, `{ days, series: [ {key, data:[{date, count}]} ] }` 형태로 두 계열을 반환한다.
- `watchlist_total`: 각 날짜 D 기준 현재 항목 중 `created_at <= D 끝시각` 개수(단조 비감소,
  마지막 날 == 현재 `total_count`).
- `risk_increasing`: 각 날짜 D 기준 현재 watchlist 자산 중 활성 RISK_ALERT 보유 고유 자산 수
  (`created_at <= D 끝시각 AND (expires_at IS NULL OR expires_at > D 끝시각)`, 마지막 날 ==
  현재 `risk_increasing_count`).
- 윈도우 전체 날짜가 0채움으로 존재하고, 빈 watchlist는 404가 아니라 전 구간 0 계열로 응답한다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- 미러 대상(대시보드 추이, 이미 머지됨):
  - 라우트 `app/api/v1/endpoints/dashboard.py`의 `GET /dashboard/trends?days=14`
    (`days: Annotated[int, Query(ge=1, le=90)] = 14`, auth `get_current_user`).
  - 서비스 `app/domains/dashboard/trend_service.py`의 `DashboardTrendService.get_trends`:
    `today = utc_now().date()`, `start_date = today - timedelta(days=days-1)`, 날짜 리스트 생성,
    일별 카운트 후 0채움 series 조립. 날짜 윈도우·0채움 패턴을 그대로 미러한다.
  - 스키마 `app/domains/dashboard/schema.py`: `TrendDataPoint{date:str, count:int}`·
    `TrendSeries{key:str, data:list[TrendDataPoint]}`·`DashboardTrendSeriesResponse{days:int, series}`.
- watchlist 현재 구조:
  - `app/domains/watchlists/service.py`의 `get_summary`가 `_get_owned_watchlist(watchlist_id, user_id)`로
    ownership 가드. `total_count = item_repo.count_by_watchlist`, `risk_increasing_count =
    signal_repo.count_assets_with_active_signal(asset_ids, SignalType.RISK_ALERT.value)`.
  - `WatchlistItem`(`app/domains/watchlists/model.py`)은 `TimestampMixin`(created_at)·hard-delete.
  - `SignalRepository.count_assets_with_active_signal`(`app/domains/signals/repository.py`)은
    `select(count(distinct Signal.asset_id)).where(asset_id.in_(...), signal_type==...,
    _active_clause())`. `_active_clause()`가 활성(미만료) 판정. Signal은 `created_at`·`expires_at` 보유.
  - watchlist 라우트는 `app/api/v1/endpoints/watchlists.py`, `/{watchlist_id}/...` 패턴.
- 코호트 제약: hard-delete라 과거 멤버십 이력이 없으므로 **현재 watchlist 코호트를 고정 기준**으로
  각 날짜의 as-of 값을 계산한다("현재 관심종목 기준 과거 추이"). 삭제된 종목은 반영되지 않는다.
- 날짜 단위: UTC 캘린더 날짜(YYYY-MM-DD), 062와 동일 UTC 기준.

## Implementation Scope

- `app/domains/watchlists/schema.py` — watchlist 도메인에 병렬 스키마 추가(대시보드
  TrendSeries/TrendDataPoint를 import하지 않고 독립 선언, 와이어 형태는 동일):
  - `WatchlistSummaryTrendDataPoint { date: str; count: int }`
  - `WatchlistSummaryTrendSeries { key: str; data: list[WatchlistSummaryTrendDataPoint] }`
  - `WatchlistSummaryTrendResponse { days: int; series: list[WatchlistSummaryTrendSeries] }`
- `app/domains/watchlists/trend_service.py` — 신규 `WatchlistSummaryTrendService`:
  - `get_trends(self, watchlist_id: int, user_id: int, days: int) -> WatchlistSummaryTrendResponse`.
  - 순서: (1) ownership 가드(`_get_owned_watchlist` 재사용, 미존재 404·비소유 403), (2) 현재 항목의
    `(asset_id, created_at)` 목록 확보, (3) 062 패턴으로 날짜 윈도우 생성, (4) `watchlist_total`
    as-of 계산(각 날짜 D에 `created_at <= D 끝시각` 항목 수), (5) `risk_increasing` as-of 계산
    (각 날짜 D에 §활성 기준 적용 고유 자산 수, asset_ids 한정), (6) 0채움 후 응답 조립.
  - `risk_increasing` as-of 조회는 날짜 D를 기준 시각으로 받는 활성 카운트가 필요하다.
    `SignalRepository`에 날짜 기준 as-of 메서드를 신규 추가하거나 서비스 내에서 직접 조합한다.
    활성 시각 조건은 기존 `_active_clause`와 동일 의미(created_at <= 기준, expires_at null 또는
    > 기준)로 맞춰 마지막 날 일관성을 보장한다.
- `app/api/v1/endpoints/watchlists.py` — 라우트 추가:
  `GET /{watchlist_id}/summary/trends`, `days: Annotated[int, Query(ge=1, le=90)] = 14`,
  auth `get_current_user`, `success(WatchlistSummaryTrendService(db).get_trends(...))`.
- 테스트 추가(아래 Test Requirements).

## Out of Scope

- FE 변경(별도 repo, 본 PR 머지 후 FE #96에서 진행).
- 기존 `GET /watchlists/{watchlist_id}/summary`(`get_summary`) 동작 변경.
- 대시보드 추이 변경, DB 스키마 변경(기존 컬럼 재사용), 캐시 전략.
- `days` 외 파라미터·주별/월별 집계·per-symbol 가격.

## Protected Files

없음. 위 Implementation Scope 밖 파일은 변경하지 않는다. 특히 기존 watchlist summary·
대시보드 추이 동작은 건드리지 않는다.

## Requirements

- 대시보드 추이의 날짜 윈도우·0채움·응답 와이어 형태를 미러한다(FE가 동일 파서 재사용 가능).
- ownership 가드를 기존 `_get_owned_watchlist`로 재사용한다.
- 두 계열의 마지막 날 값이 현재 `total_count`·`risk_increasing_count`와 각각 일치한다.
- 스키마는 watchlist 도메인에 독립 선언한다(대시보드 스키마 import 금지, 도메인 결합 방지).

## Test Requirements

- Ownership: 미존재 404, 다른 user 소유 403, 인증 없음 401.
- `watchlist_total`: 서로 다른 created_at 항목에서 날짜별 누적이 단조 비감소, 마지막 날 ==
  `total_count`, 윈도우 시작 이전 추가 항목은 첫날부터 포함, 빈 watchlist는 전 구간 0.
- `risk_increasing`: 만료된 RISK_ALERT는 만료일 이후 제외·활성 구간엔 포함, 같은 자산 복수
  신호는 1로 집계, 마지막 날 == 현재 `risk_increasing_count`.
- 0채움: 변화 없는 날은 직전 날과 동일 값, 윈도우 전체 날짜 존재.
- `days` 경계: `days=1`·`days=90` 정확한 길이, `days=0`·`days=91`는 422.
- API 계약: 응답 envelope 형태, series key 집합(`watchlist_total`·`risk_increasing`), `days` 일치.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/063-watchlist-summary-trends.md`가 근거(브랜치 포함). 계약 정렬 문서
갱신은 orchestrator가 리뷰 시 판단한다.

## ADR Need

불필요. 기존 추이(062)·ownership 패턴을 재사용하는 읽기 전용 조회이며 신규 아키텍처 결정이 없다.

## Failure Record Need

불필요.

## Risk Level

Low. 읽기 전용 파생 조회이며 미러 선례(062)가 있다. 주의점은 as-of 계산의 마지막 날
일관성(기존 활성 판정과 동일 시각 조건)·0채움·ownership 가드·스키마 도메인 독립 정도다.

## Expected Output

- 위 scope의 스키마·서비스·라우트·테스트 변경.
- 검증 3종(ruff·mypy·pytest) 통과 로그.
- 가정(현재 코호트 as-of·마지막 날 일관성·0채움)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files or existing summary/dashboard behavior.
- Report assumptions and verification results.

## Stop Conditions

- 기존 `_active_clause` 활성 판정을 날짜 as-of로 재현할 수 없어 마지막 날 일관성이 깨지면
  멈추고 보고한다.
- `WatchlistItem`에 `created_at`이 없거나 asset_id 접근이 불가하면 멈추고 보고한다.
