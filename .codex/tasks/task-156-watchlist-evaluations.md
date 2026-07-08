# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/234

## Task Summary

관심종목 항목별 평가 배지 4종(뉴스 위험도·밸류에이션 부담·테마 과열·AI 판단)을 반환하는
온디맨드 LLM 엔드포인트를 신설하고, 평가 집계값(추가 리서치 필요 수·평균 현금 연관도)을
응답에 포함한다. 아울러 PR #235 리뷰 후속 항목으로 `WatchlistSparklineService`의 404 제외
경로 테스트를 보완한다.

## Goal

- `GET /api/v1/watchlists/{watchlist_id}/evaluations`가 항목별 평가 4종과 집계 필드를
  반환한다.
- `needs_research_count`는 `news_risk == "HIGH"` OR `ai_judgment == "RISK_INCREASING"` 조건
  에 해당하는 종목 수를 반환한다.
- `cash_relevance_avg`는 `ai_judgment == "WATCH"` 종목 비율(0.0–1.0)을 반환한다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 세 검증 명령이 통과한다.

## Background

설계 문서: `docs/designs/234-watchlist-evaluations.md`

설계 문서의 Verified Facts에 현재 코드 위치를 검증해 두었다. 구현 전 실코드와 대조하고
불일치하면 보고 후 실코드를 우선하라.

**이슈 해석 변경 (설계 결정 5)**: 이슈는 `WatchlistSummaryResponse` 확장을 명시하고 있으나,
두 집계 필드 모두 LLM 평가 결과에서 파생된다. summary 엔드포인트에 LLM 의존성을 끌어들이는
것을 피하기 위해 두 필드를 `WatchlistEvaluationsResponse`에 포함하는 것으로 설계를
결정했다. `WatchlistSummaryResponse`는 변경하지 않는다.

**평균 현금 연관도 Open Question**: 제품팀 정의가 없다. 잠정 정의(`ai_judgment == "WATCH"`
종목 비율)로 구현한다. 정의 변경 시 서비스 레이어 집계 로직만 교체한다.

선행: #233(PR #235 머지 완료) — schema 충돌 없음.

## Implementation Scope

설계 문서의 Interfaces 절을 따른다.

### 신규 파일

**`app/domains/watchlists/types.py`**

평가 4종 enum:

- `NewsRisk(str, Enum)`: `HIGH`, `MEDIUM`, `LOW`
- `ValuationBurden(str, Enum)`: `HIGH`, `MODERATE`, `LOW`
- `ThemeHeat(str, Enum)`: `OVERHEATED`, `NEUTRAL`, `COLD`
- `AiJudgment(str, Enum)`: `RISK_INCREASING`, `WATCH`, `STABLE`

**`app/adapters/llm/prompts/watchlist_evaluation.py`**

`WATCHLIST_EVALUATION_SYSTEM_PROMPT: str` 상수.
`app/adapters/llm/prompts/language.py`의 `KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION`을
포함한다. enum 값(`HIGH`, `WATCH` 등)은 JSON 키와 같이 영어 원문 그대로 유지하라는 지시를
포함한다.

**`app/domains/watchlists/evaluations_service.py`**

```
class WatchlistEvaluationsService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None
    def generate(self, watchlist_id: int, user_id: int) -> WatchlistEvaluationsResponse
    def _build_evaluation_items(self, watchlist_id: int) -> list[WatchlistEvaluationItem]
    def _get_owned_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist
```

`generate` 처리 순서:

1. `_get_owned_watchlist`로 소유 확인 (observations_service.py:62 패턴 동일)
2. `_build_evaluation_items`로 snapshot 구성:
   - `WatchlistItemRepository.list_by_watchlist` → asset_ids
   - `AssetRepository.list_by_ids` → assets
   - `get_market_provider().get_quote` → quotes (per, peg, daily_change_percent)
   - `SignalRepository.active_signal_types_by_asset` → signal status
   - `resolve_watchlist_status` 적용해 symbol별 `WatchlistEvaluationItem` 구성
3. `WatchlistEvaluationSnapshot` 조립
4. `gateway.complete_json(LLMTaskType.WATCHLIST_EVALUATION, snapshot,
   WatchlistEvaluationsResult, WATCHLIST_EVALUATION_SYSTEM_PROMPT)`
5. `WatchlistEvaluationsResult.model_validate(result.output)`
6. projection 생성:
   - `items`: symbol이 snapshot에 있는 결과만 포함 (LLM hallucination 방어)
   - `needs_research_count`: `news_risk == NewsRisk.HIGH.value` OR
     `ai_judgment == AiJudgment.RISK_INCREASING.value`인 항목 수
   - `cash_relevance_avg`: `ai_judgment == AiJudgment.WATCH.value`인 항목 수 /
     전체 결과 항목 수 (항목 없으면 0.0)
   - `generated_at`: `utc_now()`

**`tests/test_watchlist_evaluations.py`** (신규)

Test Requirements 절 참고.

### 수정 파일

**`app/adapters/llm/types.py`**

`LLMTaskType`에 `WATCHLIST_EVALUATION = "WATCHLIST_EVALUATION"` 추가.

**`app/adapters/llm/schema.py`**

신규 클래스 추가:

```
class ItemEvaluationResult(BaseModel):
    symbol: str
    news_risk: str
    valuation_burden: str
    theme_heat: str
    ai_judgment: str

class WatchlistEvaluationsResult(BaseModel):
    items: list[ItemEvaluationResult]
```

**`app/adapters/llm/privacy.py`**

신규 클래스 추가:

```
class WatchlistEvaluationItem(BaseModel):
    symbol: str
    status: str
    per: Decimal | None
    peg: Decimal | None
    daily_change_percent: Decimal

class WatchlistEvaluationSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED
    watchlist_id: int
    item_count: int
    items: list[WatchlistEvaluationItem]
```

**`app/domains/watchlists/schema.py`**

신규 클래스 추가:

```
class WatchlistItemEvaluationProjection(BaseModel):
    symbol: str
    news_risk: str
    valuation_burden: str
    theme_heat: str
    ai_judgment: str

class WatchlistEvaluationsResponse(BaseModel):
    items: list[WatchlistItemEvaluationProjection]
    needs_research_count: int
    cash_relevance_avg: float
    generated_at: UtcDatetime
```

기존 클래스(`WatchlistSummaryResponse` 등)는 변경하지 않는다.

**`app/api/v1/endpoints/watchlists.py`**

신규 엔드포인트 추가:

```
GET /{watchlist_id}/evaluations
  Response: ApiResponse[WatchlistEvaluationsResponse]
  Auth: 인증 필요
  Handler: WatchlistEvaluationsService(db, get_llm_gateway()).generate(watchlist_id, current_user.id)
```

패턴: `observations` 엔드포인트(watchlists.py:200)와 동일.

---

## 후속 항목: PR #235 리뷰 S1 보완

> 출처: `docs/reviews/pr-235.md` — Suggestions S1

`WatchlistSparklineService`가 `AppException`을 잡아 `status_code == 404` AND
`error_code == ErrorCode.PRICE_SERIES_NOT_FOUND` 두 조건을 확인한 뒤 해당 종목을 결과에서
제외하는 동작을 검증하는 테스트가 없다. 현재 `tests/test_watchlist_sparklines.py` 어디에도
이 분기를 관통하는 케이스가 없다.

이번 구현 범위 안에서 다음 테스트를 추가한다.

**`tests/test_watchlist_sparklines.py`** — 기존 파일에 케이스 추가:

- `PriceSeriesService.get_series`가 `PRICE_SERIES_NOT_FOUND` 코드와 `status_code=404`를 가진
  `AppException`을 던지는 종목이 있을 때, 해당 종목만 `items`에서 빠지고 나머지 종목은
  정상 반환된다
- `AppException`이 404이되 `error_code`가 `PRICE_SERIES_NOT_FOUND`가 아닌 경우는 제외하지
  않고 예외를 재발생시킨다 (sparkline_service의 실제 예외 처리 로직에 따라 동작 확인 후 작성)

구현 전 `app/domains/watchlists/sparkline_service.py`의 실제 예외 처리 코드를 확인해
테스트가 실제 분기를 정확히 관통하도록 픽스처를 구성하라. `ErrorCode.PRICE_SERIES_NOT_FOUND`
출처는 `app/core/error_codes.py`에서 인용하고 주석을 남긴다.

---

## Out of Scope

- `WatchlistSummaryResponse` 필드 변경 (Background의 이슈 해석 변경 참고)
- 평가 결과 DB 저장·이력 관리
- 종목별 개별 뉴스 count snapshot 입력
- FE 구현 (`project_stock_frontend#117` Phase 3)
- 평가 배치 사전 생성·스케줄러
- 기존 파일의 리팩터링·네이밍 변경

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- enum 값은 반드시 `app/domains/watchlists/types.py`에 정의된 값만 사용한다.
  소문자 또는 정의되지 않은 문자열 사용 금지.
- LLM 응답의 symbol이 snapshot의 `items`에 없으면 결과에서 제외한다
  (hallucination 방어, observations_service.py의 asset 조회 실패 제외 패턴 동일).
- `needs_research_count` 기준은 `news_risk == "HIGH"` OR `ai_judgment == "RISK_INCREASING"`.
  다른 조건 추가 금지.
- `cash_relevance_avg` 기준은 `ai_judgment == "WATCH"` 종목 비율. 항목 0개이면 `0.0`.
- 빈 관심종목(`items`가 없을 때)은 `WatchlistEvaluationsResponse(items=[],
  needs_research_count=0, cash_relevance_avg=0.0, generated_at=...)` 반환 (에러 아님).
- `WatchlistEvaluationsService.__init__`은 `observations_service.py:33`·`recommendations_service.py:38`
  패턴과 동일하게 `(db: Session, gateway: LLMGateway)`를 받는다.
- 기존 `/observations`, `/recommendations`, `/sparklines`, `/summary` 응답 계약을
  변경하지 않는다.

## Test Requirements

**`tests/test_watchlist_evaluations.py`** (신규):

- `generate` 정상 경로: LLM mock이 유효한 `WatchlistEvaluationsResult`를 반환할 때
  응답 projection이 올바르게 구성됨
- `needs_research_count` 집계: `news_risk="HIGH"` 케이스, `ai_judgment="RISK_INCREASING"`
  케이스, 두 조건 모두인 케이스, 해당 없는 케이스 각각
- `cash_relevance_avg` 집계: `ai_judgment="WATCH"` 종목 비율이 정확히 계산됨, 0개일 때 `0.0`
- 빈 관심종목 → `items=[], needs_research_count=0, cash_relevance_avg=0.0`
- `GET /watchlists/{id}/evaluations` 엔드포인트 통합 테스트
- 픽스처 enum 값은 `app/domains/watchlists/types.py` 실제 정의에서 인용, 출처 주석 필수

**`tests/test_watchlist_sparklines.py`** (기존 파일 케이스 추가):

- `PRICE_SERIES_NOT_FOUND` 404 분기 제외 동작 (후속 항목 절 참고)

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

구현 완료 후 `docs/designs/234-watchlist-evaluations.md`의 Status를 `Implemented`로 갱신한다.

## ADR Need

불필요. 온디맨드 LLM + 게이트웨이 캐시 방식은 observations/recommendations 선례와 동일하며,
child endpoint 패턴도 기존 선례(/summary/trends, /sparklines)가 있다.

## Failure Record Need

불필요.

## Risk Level

Medium — `LLMTaskType`·`LLMGateway.complete_json` 경로에 신규 task type을 추가한다. gateway
캐시·budget 소비는 기존 경로와 동일하게 처리되며 별도 변경이 없다. enum 픽스처 값의 출처
불일치가 라운드4 유형 결함을 재현할 수 있으므로, 픽스처 작성 시 반드시 `types.py`에서
직접 인용해야 한다.

## Expected Output

- 신규·수정 파일 목록 보고
- 검증 3종 실행 결과 보고
- 설계 Verified Facts 인용 위치의 실제 코드 일치 여부 보고
- `cash_relevance_avg` Open Question 처리 방식 (잠정 정의 적용 여부) 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- `origin/dev`에서 `feat/234-watchlist-evaluations` 브랜치를 생성해 작업한다.
- PR은 `dev` 브랜치를 대상으로 한다 (`main` 대상 금지).
- 커밋하지 않는다.
