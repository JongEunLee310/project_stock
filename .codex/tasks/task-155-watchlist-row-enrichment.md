# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/233

## Task Summary

관심종목 확장 조회 응답에 항목별 상태 배지·시세 기준 시각을 추가하고, 관심종목 단위 1D
스파크라인 배치 엔드포인트를 신설한다.

## Goal

- `GET /watchlists/{id}/items?expand=asset` 응답의 각 item에 `status` 필드, asset에
  `reference_at` 필드가 포함된다.
- `GET /watchlists/{id}/sparklines?range=1M` 엔드포인트가 관심종목 전체 종목의 최근 일봉
  종가 시리즈를 반환한다.
- 검증 3종(`uv run ruff check .` / `uv run mypy .` / `uv run pytest`) 통과.

## Background

설계 문서: `docs/designs/233-watchlist-row-enrichment.md`

설계 문서의 Verified Facts에 현재 코드 위치를 검증해 두었다. 구현 전 실코드와 대조하고
불일치하면 보고 후 실코드를 우선하라.

주요 선행 결정:
- 전일 대비 델타는 `AssetBriefResponse.change_percent`가 이미 제공하므로 BE 변경 없음.
- 스파크라인은 별도 배치 엔드포인트(`GET /watchlists/{id}/sparklines`) 방식을 선택.
  선택 근거는 설계 문서 Design Decisions 절에 기록됨.

## Implementation Scope

설계 문서의 Interfaces 절을 따른다.

**`app/domains/watchlists/schema.py`**
- `WatchlistItemExpandedResponse`에 `status: str` 필드 추가
- `AssetBriefResponse`에 `reference_at: UtcDatetime | None = None` 필드 추가
- 신규 클래스 3종 추가: `SparklineBar(date: str, close: str)`,
  `AssetSparklineResponse(symbol: str, bars: list[SparklineBar])`,
  `WatchlistSparklineResponse(items: list[AssetSparklineResponse])`

**`app/domains/watchlists/service.py`** — `list_items_expanded` 수정
- `self.signal_repo.active_signal_types_by_asset(asset_ids)` 배치 호출 추가
- 각 item에 `resolve_watchlist_status(active_types.get(item.asset_id, set()))` 적용
- `WatchlistItemExpandedResponse` 생성 시 `status` 전달
- `AssetBriefResponse` 생성 시 `reference_at=quote.as_of if quote is not None else None` 전달

**`app/domains/watchlists/sparkline_service.py`** (신규 파일)
- `WatchlistSparklineService` 클래스: 관심종목 소유 확인 → asset 목록 조회 →
  `PriceSeriesService.get_series`로 종목별 일봉 bars 조회 → close만 발췌해 반환

**`app/api/v1/endpoints/watchlists.py`**
- 신규 엔드포인트: `GET /{watchlist_id}/sparklines`
  - `range` 쿼리 파라미터: `Literal["1M", "3M", "6M", "1Y"]`, 기본값 `"1M"`
  - 응답: `ApiResponse[WatchlistSparklineResponse]`
  - 인증·소유자 확인 기존 패턴 동일하게 적용

**테스트**: Test Requirements 절의 범주 참고

## Out of Scope

- 인트라데이 스파크라인 지원
- `AssetDetailResponse` 등 다른 응답의 status·reference_at 처리
- FE 변경
- 스파크라인 외부 데이터 소스 추가
- 전일 대비 델타 신규 필드 추가 (기존 `change_percent`로 충분, 설계 결정)

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- `status` 값은 `app/domains/signals/types.py`의 `SignalType.value`(대문자) 또는
  `"NORMAL"` 중 하나여야 한다. 소문자 값 사용 금지.
- `resolve_watchlist_status` 호출 시 인자는 `set[str]` 타입이어야 한다.
  `active_signal_types_by_asset` 반환값의 타입과 일치함을 확인하라.
- `reference_at`은 `QuoteResult.as_of`를 전달한다. 필드명은 기존 시장 도메인 표기 규칙
  (`IndexQuoteResult.reference_at`)과 통일한다.
- 스파크라인 응답의 `close`는 `PriceSeriesService`의 `_decimal_to_wire` 규칙과 동일하게
  문자열로 전달한다.
- `WatchlistItemExpandedResponse`·`AssetBriefResponse` 변경은 기존 필드·직렬화 형태를
  변경하지 않는다 (필드 추가만, FE 하위 호환).
- 빈 관심종목에 대한 스파크라인 요청은 `items: []`를 반환한다 (에러 아님).
- 스파크라인 서비스에서 `PriceSeriesService.get_series`가 404를 던지는 종목은 해당 symbol을
  결과에서 제외하고 나머지를 반환한다.

## Test Requirements

- `list_items_expanded` 반환값에 `status` 포함 테스트 (활성 시그널 없음 → `"NORMAL"`)
- `status` 우선순위 테스트: 복수 활성 시그널 중 `RISK_ALERT`·`THESIS_BROKEN` 동시 활성 시
  우선순위 최상위 반환 (`WATCHLIST_STATUS_PRIORITY` 순서 기준)
- `list_items_expanded` 반환값에 `asset.reference_at` 포함 테스트 (quote 있을 때·없을 때)
- `GET /watchlists/{id}/sparklines` 테스트:
  - range 기본값(`1M`) 동작
  - range 명시값(`3M`) 동작
  - 빈 관심종목 → `items: []` 반환
- `WatchlistSparklineService` 단위 테스트 (종목별 bars가 올바르게 발췌되는지)
- 픽스처 `SignalType.value` 는 반드시 `app/domains/signals/types.py` 실제 값에서 인용하고
  주석으로 출처를 남긴다
- 기존 확장 조회 테스트 약화·삭제 금지 (currency·change_percent 포함 테스트 등)

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

구현 완료 후 `docs/designs/233-watchlist-row-enrichment.md`의 Status를 `Implemented`로 갱신한다.

## ADR Need

불필요. 기존 signals·prices 도메인의 재사용이며, 별도 엔드포인트 패턴은 이미
`/summary/trends` 선례가 있다.

## Failure Record Need

불필요.

## Risk Level

Medium — 기존 `list_items_expanded` 경로를 수정하므로 확장 조회 응답 계약에 영향이 있다.
필드 추가만이고 기존 필드 변경이 없어 하위 호환은 유지되지만, `status`·`reference_at`
픽스처 값은 반드시 실제 생산자 코드에서 인용해야 한다.

## Expected Output

- 변경 파일 목록 보고
- 검증 3종 실행 결과 보고
- 설계 Verified Facts 인용 위치의 실제 코드 일치 여부 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- `origin/dev`에서 `feat/233-watchlist-row-enrichment` 브랜치를 생성해 작업한다.
  새 브랜치를 따로 만들지 않고 이 브랜치에서 바로 시작한다.
- PR은 `dev` 브랜치를 대상으로 한다 (`main` 대상 금지).
- 커밋하지 않는다.
