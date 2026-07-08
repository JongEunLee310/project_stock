# Design: 관심종목 항목별 평가 배지 계약 (#234)

## Status

Implemented

## Context

FE 관심종목 페이지(`project_stock_frontend#117`) Phase 3에서 테이블 행마다 평가 배지 4종
(뉴스 위험도·밸류에이션 부담·테마 과열·AI 판단)을 표시하고, 집계 카드에 추가 리서치 필요
종목 수와 평균 현금 연관도를 표시해야 한다. 이를 제공하는 BE 계약이 현재 없다.

선행 이슈 #233(PR #235, 관심종목 행 보강)이 머지되어 있으므로 schema·endpoint 충돌 없이
진행할 수 있다.

## Verified Facts (origin/dev, 2026-07-08 확인)

- `app/domains/watchlists/observations_service.py:33` —
  `WatchlistObservationsService.__init__(self, db: Session, gateway: LLMGateway)` —
  LLM gateway 주입 패턴. `generate(watchlist_id, user_id)` 온디맨드 LLM 호출.
- `app/domains/watchlists/recommendations_service.py:38` —
  `WatchlistRecommendationsService.__init__(self, db: Session, gateway: LLMGateway)` —
  동일 패턴. 관심종목 전체를 단일 LLM 호출로 처리.
- `app/adapters/llm/gateway.py:59` —
  `LLMGateway.complete_json(task_type, payload, schema, system_prompt, escalation_signal=None)`
  — 캐시 조회·budget 소비·cloud 호출·캐시 저장을 단일 경로에서 처리.
- `app/adapters/llm/types.py:8` — `LLMTaskType(str, Enum)` 현재 값:
  `NEWS_SUMMARY`, `THESIS_CONFLICT`, `PORTFOLIO_BRIEFING`, `DASHBOARD_BRIEFING`,
  `WATCHLIST_NOTE`, `STOCK_RECOMMENDATION`, `TAG_SENTIMENT`, `AGENT`.
  `WATCHLIST_EVALUATION`은 없음 — 신규 추가 필요.
- `app/adapters/llm/privacy.py:121` — `WatchlistObservationSnapshot(CloudSafePayload)`:
  `sensitivity = SensitivityLevel.AGGREGATED`, 필드: `watchlist_id: int`, `item_count: int`,
  `items: list[WatchlistHighlight]`.
- `app/adapters/llm/privacy.py:80` — `WatchlistHighlight(BaseModel)`:
  `symbol: str`, `status: str`, `per: Decimal | None`, `peg: Decimal | None`,
  `daily_change_percent: Decimal`.
- `app/adapters/llm/prompts/language.py:1` —
  `KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION` 상수. 신규 프롬프트도 이 상수를 포함한다.
- `app/domains/watchlists/schema.py:86` —
  `WatchlistSummaryResponse(total_count: int, risk_increasing_count: int,
  recent_items: list[RecentWatchlistItemResponse])`. 현재 3개 필드만 존재.
- `app/api/v1/endpoints/watchlists.py:200` —
  `/observations` 엔드포인트: `WatchlistObservationsService(db, get_llm_gateway()).generate(...)`.
  child endpoint 패턴 (`/sparklines`, `/observations`, `/recommendations` 동일 형식).
- `app/domains/raw_news/repository.py:10` — `RawNewsEventRepository`는 `create_or_skip`,
  `get_by_url`, `mark_normalized`, `mark_failed`만 제공. 종목별 최근 뉴스 조회 메서드 없음.
  뉴스 위험도 입력은 현재 시그널·시세 지표에서 LLM이 추론하도록 한다 — 이후 뉴스 count 제공
  시 snapshot 확장 가능.

## Design Decisions

### 1. 생성·캐싱 방식: 온디맨드 LLM 호출 + 게이트웨이 캐시

observations와 recommendations 선례를 그대로 따른다. `LLMGateway.complete_json`이 이미
CLOUD 경로에서 `LLMResponseCache`를 통한 캐시 조회·저장을 처리하므로 서비스 레이어에서
별도 캐시 로직을 추가하지 않는다.

배치 사전 생성(별도 스케줄러로 미리 평가 결과를 DB에 저장) 방식도 검토했으나, 스케줄러
인프라가 없고 관심종목이 수시로 변경되어 재생성 타이밍이 복잡해진다. 온디맨드 방식이
관리 복잡도 면에서 현 단계에 적합하고, 게이트웨이 캐시가 반복 호출 비용을 흡수한다.

종목별 개별 LLM 호출이 아니라 관심종목 내 항목 전체를 단일 호출의 입력으로 넣어 결과를
받는 방식을 선택한다. observations·recommendations의 배치 처리 방식과 동일하다.

### 2. 평가 4종 enum 정의

신규 Python enum 4종을 `app/domains/watchlists/types.py`(신규 파일)에 정의한다.
LLM은 문자열 값을 반환하고 서비스 레이어에서 유효성 검증한다.

| enum 클래스 | 값 | FE 배지 한국어 라벨 |
|---|---|---|
| `NewsRisk.HIGH` | `"HIGH"` | 위험 |
| `NewsRisk.MEDIUM` | `"MEDIUM"` | 주의 |
| `NewsRisk.LOW` | `"LOW"` | 양호 |
| `ValuationBurden.HIGH` | `"HIGH"` | 고평가 |
| `ValuationBurden.MODERATE` | `"MODERATE"` | 보통 |
| `ValuationBurden.LOW` | `"LOW"` | 저평가 |
| `ThemeHeat.OVERHEATED` | `"OVERHEATED"` | 과열 |
| `ThemeHeat.NEUTRAL` | `"NEUTRAL"` | 중립 |
| `ThemeHeat.COLD` | `"COLD"` | 냉각 |
| `AiJudgment.RISK_INCREASING` | `"RISK_INCREASING"` | 위험 증가 |
| `AiJudgment.WATCH` | `"WATCH"` | 관망 |
| `AiJudgment.STABLE` | `"STABLE"` | 안정 |

### 3. "추가 리서치 필요" 산출 기준

LLM 응답을 받은 뒤 서비스 레이어에서 다음 조건에 해당하는 종목을 집계한다.

```
news_risk == "HIGH" OR ai_judgment == "RISK_INCREASING"
```

이 기준은 코드에 명시적으로 표현된다. LLM에 `needs_research` 판단을 위임하지 않으므로
LLM 자유도 변동이 집계값에 영향을 주지 않는다.

### 4. "평균 현금 연관도" 산출 기준 (Open Question)

"평균 현금 연관도"는 디자인 시안의 표현이며 제품팀 정의가 없다. 잠정 정의를 제안한다.

**잠정 정의**: AI 판단이 `"WATCH"`인 종목 수를 전체 항목 수로 나눈 비율(float, 0.0–1.0).
방어적 관망 종목 비중이 높을수록 현금 확보 필요성이 높다는 의미로 해석한다.

이 정의는 프로덕트 결정 없이 제안된 것이다. 제품팀이 다른 정의(예: 포트폴리오 현금
비중 연동, 배당주 비중 등)를 원할 경우 산출 로직만 교체하면 된다. **구현 전 제품팀
확인이 필요하다.** Open Question 섹션에 추적 항목으로 명시한다.

### 5. summary 필드 확장 위치

이슈는 `WatchlistSummaryResponse` 확장을 명시하고 있으나, 두 필드(`needs_research_count`,
`cash_relevance_avg`) 모두 LLM 평가 결과에서 파생된다. `WatchlistService.get_summary`에
LLM 의존성을 끌어들이면 빠른 DB 기반 집계 응답이라는 현재 summary의 성격이 깨진다.

**결정**: 두 필드를 `WatchlistEvaluationsResponse`에 포함한다. FE는 evaluations API
한 번으로 배지 데이터와 집계값을 함께 받는다. `WatchlistSummaryResponse`는 변경하지 않는다.
이 결정을 이슈 해석 변경으로 핸드오프에 명시해 Codex가 혼란 없이 구현하도록 한다.

### 6. 엔드포인트 형태

`/observations`, `/recommendations`, `/sparklines` 선례를 따라
`GET /api/v1/watchlists/{watchlist_id}/evaluations` child endpoint를 신설한다.

### 7. ADR 필요 여부

불필요. 온디맨드 LLM + 게이트웨이 캐시 방식은 observations/recommendations 선례와 동일하며
새로운 아키텍처 결정이 없다. child endpoint 패턴도 기존 선례가 있다.

## Interfaces

### 신규 파일: `app/domains/watchlists/types.py`

```
class NewsRisk(str, Enum): HIGH, MEDIUM, LOW
class ValuationBurden(str, Enum): HIGH, MODERATE, LOW
class ThemeHeat(str, Enum): OVERHEATED, NEUTRAL, COLD
class AiJudgment(str, Enum): RISK_INCREASING, WATCH, STABLE
```

### LLM 입력 snapshot (신규, `app/adapters/llm/privacy.py`)

```
class WatchlistEvaluationItem(BaseModel):
    symbol: str
    status: str          # SignalType.value 또는 "NORMAL"
    per: Decimal | None
    peg: Decimal | None
    daily_change_percent: Decimal

class WatchlistEvaluationSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.AGGREGATED
    watchlist_id: int
    item_count: int
    items: list[WatchlistEvaluationItem]
```

### LLM 출력 schema (신규, `app/adapters/llm/schema.py`)

```
class ItemEvaluationResult(BaseModel):
    symbol: str
    news_risk: str          # NewsRisk 값
    valuation_burden: str   # ValuationBurden 값
    theme_heat: str         # ThemeHeat 값
    ai_judgment: str        # AiJudgment 값

class WatchlistEvaluationsResult(BaseModel):
    items: list[ItemEvaluationResult]
```

### `LLMTaskType` 추가 (`app/adapters/llm/types.py`)

```
WATCHLIST_EVALUATION = "WATCHLIST_EVALUATION"
```

### 신규 프롬프트 (`app/adapters/llm/prompts/watchlist_evaluation.py`)

```
WATCHLIST_EVALUATION_SYSTEM_PROMPT: str
```

`KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION`을 포함한다. enum 값은 JSON 키와 같이 원문
그대로 유지한다는 지시를 포함한다.

### 응답 projection (`app/domains/watchlists/schema.py`)

신규 클래스:

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

### WatchlistEvaluationsService (신규, `app/domains/watchlists/evaluations_service.py`)

```
class WatchlistEvaluationsService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None
    def generate(self, watchlist_id: int, user_id: int) -> WatchlistEvaluationsResponse
    def _build_evaluation_items(self, watchlist_id: int) -> list[WatchlistEvaluationItem]
    def _get_owned_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist
```

`generate` 책임: 소유 확인 → 항목 snapshot 구성 →
`gateway.complete_json(WATCHLIST_EVALUATION, snapshot, WatchlistEvaluationsResult, WATCHLIST_EVALUATION_SYSTEM_PROMPT)` 호출 →
결과 projection 생성 → `needs_research_count` 집계 (조건: `news_risk == "HIGH"` OR
`ai_judgment == "RISK_INCREASING"`) → `cash_relevance_avg` 집계 (잠정: `ai_judgment ==
"WATCH"` 종목 비율) → `WatchlistEvaluationsResponse` 반환.

### API (신규)

```
GET /api/v1/watchlists/{watchlist_id}/evaluations
  Response: ApiResponse[WatchlistEvaluationsResponse]
  Auth: 인증 필요, 소유자 확인
```

## Dependencies

- `app/adapters/llm.gateway` — `LLMGateway.complete_json`
- `app/adapters/factory` — `get_llm_gateway()`
- `app/adapters/llm.privacy` — `CloudSafePayload`, `WatchlistEvaluationSnapshot`
- `app/domains/signals` — `SignalRepository.active_signal_types_by_asset`, `resolve_watchlist_status`
- `app/adapters/market` — `get_market_provider().get_quote` (per/peg/change_percent 수집)
- `app/domains/assets` — `AssetRepository`
- `app/domains/watchlists` — `WatchlistRepository`, `WatchlistItemRepository`

## Out of Scope

- `WatchlistSummaryResponse` 필드 변경 (Design Decisions 5 참고)
- 평가 결과 DB 저장·이력 관리
- 종목별 개별 뉴스 count snapshot 입력 (raw_news 도메인 확장 시 후속)
- FE 구현 (`project_stock_frontend#117` Phase 3)
- 평가 배치 사전 생성·스케줄러

## Test Strategy

- `WatchlistEvaluationsService.generate` — 온디맨드 LLM 호출, 결과 projection 반환
- `needs_research_count` 집계 기준 검증: `news_risk == "HIGH"` 또는 `ai_judgment ==
  "RISK_INCREASING"` 중 하나라도 해당하는 종목 수
- `cash_relevance_avg` 집계 기준 검증: `ai_judgment == "WATCH"` 종목 비율 (Open Question
  해소 전 잠정 기준)
- 빈 관심종목(items가 없을 때) — `WatchlistEvaluationsResponse(items=[], needs_research_count=0,
  cash_relevance_avg=0.0)`
- `GET /watchlists/{id}/evaluations` 엔드포인트 통합 테스트
- LLM schema 유효성: LLM 응답의 enum 값이 `NewsRisk`, `ValuationBurden`, `ThemeHeat`,
  `AiJudgment` 정의값과 일치하는지 — enum 값 픽스처는 `app/domains/watchlists/types.py`
  실제 정의에서 인용하고 출처 주석을 남긴다
- 기존 `/observations`, `/recommendations`, `/summary` 테스트 약화·삭제 금지

## Open Questions

1. **평균 현금 연관도 정의** — 제품팀이 "현금 연관도"를 어떤 지표로 정의하는지 확인이
   필요하다. 현재 잠정 정의(`ai_judgment == "WATCH"` 비율)로 구현하되, 결정 변경 시
   서비스 레이어 집계 로직만 교체한다.
