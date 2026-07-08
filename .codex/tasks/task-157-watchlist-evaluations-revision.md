# Codex Handoff Task

## Source Issue

PR #236 리뷰 후속 / 이슈 #234 수정 설계 R1
설계 문서: `docs/designs/234-watchlist-evaluations.md` (R1)

## Task Summary

PR #236에서 구현된 evaluations 엔드포인트에 세 가지 변경을 적용한다.
(1) `cash_relevance_avg` 필드를 `WatchlistEvaluationsResponse`에서 제거한다.
(2) "신규 매수 여력(buy_readiness)"을 `WatchlistSummaryResponse` 확장으로 신규 구현한다.
(3) PR #236 리뷰 S1·S2·Q1을 반영한 방어 처리 및 주석을 추가한다.
현재 체크아웃된 브랜치 `feat/234-watchlist-evaluations`에서 작업한다.

## Goal

다음이 모두 성립할 때 완료다.

- `GET /api/v1/watchlists/{watchlist_id}/evaluations` 응답에서 `cash_relevance_avg` 필드가 사라진다.
- `GET /api/v1/watchlists/{watchlist_id}/summary`가 `buy_readiness` 필드를 반환한다.
  - `portfolio_id` 쿼리 파라미터를 제공하거나, 미제공 시 사용자의 첫 번째 포트폴리오(id 오름차순)를 사용한다.
  - 포트폴리오가 없으면 `buy_readiness: null`을 반환한다.
- LLM이 enum 외 값을 반환해도 해당 항목만 스킵되고 전체 요청은 실패하지 않는다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 세 검증 명령이 모두 통과한다.

## Background

설계 결정 배경을 요약한다. 상세는 `docs/designs/234-watchlist-evaluations.md` R1을 읽어라.

**cash_relevance_avg 폐기 이유**: 제품 의도에 맞지 않는다고 개발자가 확정했다. 대신
"신규 매수 여력(buy_readiness)"으로 대체한다. buy_readiness는 포트폴리오 현금 비중과
관심종목 내 BUY_CANDIDATE 시그널 종목 수를 조합한 결정적 계산이며, LLM에 의존하지 않는다.

**배치 역전**: R0 설계는 두 집계를 `WatchlistEvaluationsResponse`에 포함했다. R1에서
buy_readiness가 LLM 파생이 아님이 확정됐으므로 `WatchlistSummaryResponse` 확장이 적합하다.
summary는 빠른 DB 집계 성격을 유지하며, buy_candidate_count는 순수 DB 집계,
cash_weight는 PortfolioService.get_summary로 결정적 계산이 가능하다.

**포트폴리오 선택**: 기존 briefing_service는 portfolio_id를 명시적으로 받는다. summary
엔드포인트에는 optional `portfolio_id` 쿼리 파라미터를 추가한다. 미지정 시
`PortfolioRepository.list_by_user(user_id, limit=1)`로 첫 번째 포트폴리오를 자동 선택한다.
출처: `app/domains/portfolios/repository.py:16-26` — `Portfolio.id` 오름차순으로 정렬됨.

**레벨 판정 임계값 출처**: `app/domains/portfolios/service.py:33-34`
- `CASH_FLOOR_HIGH = Decimal("0.05")`
- `CASH_FLOOR_MEDIUM = Decimal("0.15")`
- `cash_weight >= 0.15` → `SUFFICIENT` / "충분"
- `0.05 <= cash_weight < 0.15` → `LIMITED` / "제한적"
- `cash_weight < 0.05` → `RESTRICTED` / "매우 제한적"

**분모 원칙(Q1)**: 비율 지표(`cash_relevance_avg`)가 제거됐으므로 직접 영향은 없다. 단,
`_project_items`에서 snapshot에 있지만 LLM 결과에 없는 symbol(누락 항목)의 수를
warning 로그로 기록하는 원칙을 유지한다.

## Implementation Scope

아래 파일만 수정한다. 다른 파일은 건드리지 않는다.

### `app/domains/watchlists/types.py` — BuyReadinessLevel 추가

기존 4종 enum은 변경 없음. 다음을 추가한다.

```
class BuyReadinessLevel(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    LIMITED = "LIMITED"
    RESTRICTED = "RESTRICTED"
```

### `app/domains/watchlists/schema.py`

신규 클래스 추가:

```
class BuyReadinessProjection(BaseModel):
    level: str
    level_label: str
    cash_weight: Decimal
    buy_candidate_count: int
    message: str
```

`WatchlistSummaryResponse` 변경 — `buy_readiness` 필드 추가:

```
class WatchlistSummaryResponse(BaseModel):
    total_count: int
    risk_increasing_count: int
    recent_items: list[RecentWatchlistItemResponse]
    buy_readiness: BuyReadinessProjection | None
```

`WatchlistEvaluationsResponse` 변경 — `cash_relevance_avg` 필드 제거:

```
class WatchlistEvaluationsResponse(BaseModel):
    items: list[WatchlistItemEvaluationProjection]
    needs_research_count: int
    generated_at: UtcDatetime
```

### `app/domains/watchlists/service.py`

`WatchlistService.__init__`에 `PortfolioRepository` 추가.

`get_summary` 시그니처 변경:

```
def get_summary(
    self,
    watchlist_id: int,
    user_id: int,
    portfolio_id: int | None = None,
    recent_limit: int = 5,
) -> WatchlistSummaryResponse
```

`buy_readiness` 계산 로직:
1. `portfolio_id`가 주어지면 그대로 사용. 없으면 `PortfolioRepository.list_by_user(user_id, limit=1)`로 첫 번째 포트폴리오를 가져온다.
2. 포트폴리오가 없으면 `buy_readiness = None`.
3. 있으면 `PortfolioService(db).get_summary(resolved_portfolio_id, user_id).cash_weight`로 현금 비중 산출.
4. `count_assets_with_active_signal(asset_ids, SignalType.BUY_CANDIDATE.value)`로 매수 후보 수 산출.
5. 레벨 판정(Background 레벨 기준 참고) → `BuyReadinessProjection` 생성.

`PortfolioService.get_summary`는 소유 확인을 내부에서 처리하므로 별도 검증 불필요. 단, `portfolio_id`가 명시적으로 지정된 경우 다른 사용자 포트폴리오를 지정하면 403이 발생할 수 있다 — 이는 의도된 동작이다.

### `app/domains/watchlists/evaluations_service.py`

`_project_items` 방어 처리 변경: `_ValidatedEvaluation.model_validate` 호출을 `try/except ValidationError`로 감싸 해당 항목을 스킵하고 symbol과 오류 내용을 warning 레벨로 로그에 기록한다. `pydantic.ValidationError`를 import한다. 전체 요청 실패 없이 유효 항목만 반환한다.

LLM 결과에서 누락된 항목(snapshot에 있지만 LLM 결과에 없는 symbol)을 감지해 누락 수를
warning 레벨로 로그에 기록한다.

`generate` 메서드에서 `cash_relevance_avg` 계산 코드를 제거하고 `WatchlistEvaluationsResponse`
생성 시 해당 필드 참조도 제거한다.

### `app/api/v1/endpoints/watchlists.py`

`get_watchlist_summary` 핸들러에 선택적 쿼리 파라미터 추가:

```
portfolio_id: int | None = Query(default=None)
```

`WatchlistService(db).get_summary(watchlist_id, current_user.id, portfolio_id=portfolio_id, recent_limit=recent_limit)` 호출로 변경.

### `app/adapters/llm/mock.py`

`WatchlistEvaluationsResult` mock 딕셔너리 위에 주석 추가:

```python
# Enum values are sourced from app/domains/watchlists/types.py.
```

## Out of Scope

- `WatchlistEvaluationsResponse` 내 다른 필드 변경
- PR #236 이전에 존재하던 파일의 리팩터링·네이밍 변경
- 평가 결과 DB 저장·이력 관리
- FE 구현 (`project_stock_frontend#117`)
- `BuyReadinessLevel` 판정 기준의 설정화
- 기존 `/observations`, `/recommendations`, `/sparklines` 계약 변경

## Protected Files

없음.

## Requirements

- `cash_relevance_avg`가 `WatchlistEvaluationsResponse` 및 관련 서비스 코드에서 완전히 제거된다.
- `WatchlistSummaryResponse.buy_readiness`는 포트폴리오가 없을 때 `null`을 반환한다.
- 레벨 판정 임계값은 반드시 `app/domains/portfolios/service.py:33-34`의 상수를 import하거나 동일 값을 동일 이름으로 재정의해 출처를 추적 가능하게 한다. 매직 넘버 금지.
- `BuyReadinessLevel` enum 값은 `app/domains/watchlists/types.py`에서만 정의한다.
- `_project_items`의 enum 외 값 스킵은 전체 실패 없이 항목 단위로 처리한다.
- 기존 `tests/test_watchlist_evaluations.py`의 `cash_relevance_avg` 검증은 제거하되 다른 케이스는 약화하지 않는다.
- 모든 테스트 픽스처의 enum 리터럴은 실제 정의에서 인용하고 출처 주석을 남긴다.

## Test Requirements

다음 테스트를 신규 작성하거나 기존 파일에 추가한다.

**`tests/test_watchlist_summary.py` 또는 기존 summary 테스트 파일** (파일이 없으면 신규):

- `buy_readiness` 정상 경로: portfolio_id 제공 시 `PortfolioService.get_summary`에서 가져온 `cash_weight`와 `BUY_CANDIDATE` 시그널 count를 기반으로 `BuyReadinessProjection`이 올바르게 구성됨
- `portfolio_id` 미제공 시 첫 번째 포트폴리오 자동 선택
- 포트폴리오 없음 → `buy_readiness: null`
- 레벨 판정 경계값 (아래 5가지를 모두 테스트한다):
  - `cash_weight = Decimal("0.20")` → `SUFFICIENT`
  - `cash_weight = Decimal("0.15")` → `SUFFICIENT` (CASH_FLOOR_MEDIUM 경계, 포함)
  - `cash_weight = Decimal("0.14")` → `LIMITED`
  - `cash_weight = Decimal("0.05")` → `LIMITED` (CASH_FLOOR_HIGH 경계, 포함)
  - `cash_weight = Decimal("0.04")` → `RESTRICTED`
- `buy_candidate_count` 집계 정확성: `BUY_CANDIDATE` 활성 시그널 있는 종목만 집계

**`tests/test_watchlist_evaluations.py` — 기존 파일 수정**:

- `cash_relevance_avg` 검증 코드를 제거한다
- `WatchlistEvaluationsResponse`에 `cash_relevance_avg` 필드가 없음을 확인하는 케이스를 추가한다 (또는 기존 응답 구조 검증이 필드 부재를 자연스럽게 커버하도록 한다)
- enum 외 값 스킵 테스트를 추가한다: LLM mock이 일부 항목에 `"INVALID_VALUE"`를 반환해도 유효한 나머지 항목이 정상 반환된다

**모든 픽스처**:

- 레벨 판정 경계값 테스트의 `cash_weight`는 `Decimal` 타입으로 작성한다
- `CASH_FLOOR_HIGH`, `CASH_FLOOR_MEDIUM` 상수는 `app/domains/portfolios/service.py`에서 import하거나 출처 주석을 남긴다

## Verification Commands

아래 세 명령을 순서대로 실행하고 모두 통과해야 한다.

```
uv run ruff check .
uv run mypy .
uv run pytest
```

실행 결과(pass/fail 및 오류 메시지)를 보고에 포함한다.

## Documentation Impact

구현 완료 후 `docs/designs/234-watchlist-evaluations.md`의 Status를 `Implemented`로 갱신한다.

## ADR Need

불필요. 기존 결정(온디맨드 집계·summary child endpoint 패턴)과 동일한 선례 안에 있다.

## Failure Record Need

불필요.

## Risk Level

Medium — `WatchlistSummaryResponse` 스키마 변경이 기존 FE 계약에 영향을 줄 수 있다.
`buy_readiness` 필드가 추가되는 것이므로 기존 FE가 추가 필드를 무시하도록 구현된 경우
하위 호환된다. FE와 계약을 확인한 뒤 진행하는 것이 안전하다.

`PortfolioService.get_summary` 호출이 시장 데이터 조회를 유발하므로 summary 응답 시간이
늘어날 수 있다. 포트폴리오 없는 사용자는 시장 데이터 호출이 없다.

## Expected Output

- 수정된 파일 목록 및 변경 요약
- 검증 3종 실행 결과
- `buy_readiness: null` 경로와 포트폴리오 있는 경로 각각의 테스트 통과 확인
- 가정·잔여 위험 보고

## Rules

- 현재 브랜치(`feat/234-watchlist-evaluations`)를 유지한다. 새 브랜치를 만들지 않는다.
- 커밋하지 않는다.
- Implementation Scope에 나열된 파일만 수정한다.
- 기존 테스트를 약화하거나 삭제하지 않는다.
- 레벨 판정 임계값은 `app/domains/portfolios/service.py`의 상수를 근거로 사용한다. 임의 숫자를 하드코딩하지 않는다.
- `WatchlistSummaryResponse` 기존 3개 필드(`total_count`, `risk_increasing_count`, `recent_items`)를 변경하지 않는다.
- 가정이 생기면 구현 전에 기록하고 보고에 포함한다.
