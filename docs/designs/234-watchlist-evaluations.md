# Design: 관심종목 항목별 평가 배지 계약 (#234)

## Status

Implemented

## Revision History

| 버전 | 날짜 | 변경 내용 |
|---|---|---|
| R0 | 2026-07-04 | 초안 작성. |
| R1 | 2026-07-08 | PR #236 리뷰(S1·S2·Q1)와 개발자 피드백 반영. "평균 현금 연관도" 폐기, "신규 매수 여력(buy_readiness)" 재설계. 배치를 `WatchlistEvaluationsResponse`에서 `WatchlistSummaryResponse` 확장으로 역전. |

## Context

FE 관심종목 페이지(`project_stock_frontend#117`) Phase 3에서 테이블 행마다 평가 배지 4종
(뉴스 위험도·밸류에이션 부담·테마 과열·AI 판단)을 표시하고, 집계 카드에 신규 매수 여력
정보를 표시해야 한다. 이를 제공하는 BE 계약이 현재 없다.

선행 이슈 #233(PR #235, 관심종목 행 보강)이 머지되어 있으므로 schema·endpoint 충돌 없이
진행할 수 있다.

PR #236에서 evaluations 엔드포인트와 집계 2종(`needs_research_count`, `cash_relevance_avg`)이
구현되었으나, 개발자 피드백으로 `cash_relevance_avg`가 제품 의도에 맞지 않는다고 확정됐다.
R1은 해당 필드를 폐기하고 "신규 매수 여력(buy_readiness)"으로 재설계하는 수정 설계다.

## Verified Facts (origin/dev, 2026-07-08 확인)

### R0 원본 사실 (유효)

- `app/domains/watchlists/observations_service.py:33` —
  `WatchlistObservationsService.__init__(self, db: Session, gateway: LLMGateway)` —
  LLM gateway 주입 패턴.
- `app/adapters/llm/gateway.py:59` —
  `LLMGateway.complete_json(task_type, payload, schema, system_prompt, escalation_signal=None)`
- `app/adapters/llm/types.py:8` — `LLMTaskType(str, Enum)` 현재 값:
  `NEWS_SUMMARY`, `THESIS_CONFLICT`, `PORTFOLIO_BRIEFING`, `DASHBOARD_BRIEFING`,
  `WATCHLIST_NOTE`, `STOCK_RECOMMENDATION`, `TAG_SENTIMENT`, `AGENT`.
  `WATCHLIST_EVALUATION`은 PR #236에서 추가됨.
- `app/domains/watchlists/schema.py:86` — 현재 `WatchlistSummaryResponse`:
  `total_count: int`, `risk_increasing_count: int`, `recent_items: list[RecentWatchlistItemResponse]`.
- `app/domains/watchlists/schema.py:126` — 현재 `WatchlistEvaluationsResponse`:
  `items`, `needs_research_count`, `cash_relevance_avg: float`, `generated_at`.

### R1 추가 확인 사실

- `app/domains/portfolios/service.py:33` —
  `CASH_FLOOR_HIGH = Decimal("0.05")` — 현금 비중 위험 임계값.
- `app/domains/portfolios/service.py:34` —
  `CASH_FLOOR_MEDIUM = Decimal("0.15")` — 현금 비중 경고 임계값.
- `app/domains/portfolios/service.py:125-131` —
  `PortfolioService.get_summary(portfolio_id: int, user_id: int) -> PortfolioSummaryResponse` —
  소유 확인·포지션·시장가 조회를 포함한 공개 메서드.
- `app/domains/portfolios/schema.py:91` —
  `PortfolioSummaryResponse.cash_weight: Decimal` — 현금 비중(0.0–1.0). `get_summary` 반환값에 포함됨.
- `app/domains/portfolios/repository.py:16-26` —
  `PortfolioRepository.list_by_user(user_id, offset=0, limit=None) -> list[Portfolio]` —
  `Portfolio.id` 오름차순 정렬. 포트폴리오가 여럿일 때 첫 번째가 결정적으로 선택 가능.
- `app/domains/signals/repository.py:58-74` —
  `SignalRepository.count_assets_with_active_signal(asset_ids: list[int], signal_type: str) -> int` —
  WatchlistService.get_summary가 이미 `RISK_ALERT` 집계에 이 메서드를 사용함
  (`app/domains/watchlists/service.py:180-182`).
- `app/domains/signals/types.py:8` — `SignalType.BUY_CANDIDATE = "BUY_CANDIDATE"` — 매수 후보 시그널.
- `app/domains/watchlists/service.py:170-209` —
  `WatchlistService.get_summary(watchlist_id, user_id, recent_limit=5) -> WatchlistSummaryResponse` —
  현재 시그니처. `portfolio_id` 파라미터 없음. `signal_repo`가 이미 주입되어 있음.
- `app/api/v1/endpoints/watchlists.py:142-154` —
  `GET /{watchlist_id}/summary` — 현재 `portfolio_id` 쿼리 파라미터 없음.
- `app/domains/portfolios/service.py:426-444` —
  `_calculate_risk_exposures`에서 `cash_weight < CASH_FLOOR_HIGH` → `"HIGH"`,
  `cash_weight < CASH_FLOOR_MEDIUM` → `"MEDIUM"`으로 현금 부족 노출을 판정하는 선례가 있음.
  buy_readiness 레벨 판정은 이 임계값 조합을 역전시켜 적용한다.

## Design Decisions

### R1 개정 결정

#### R1-1. "평균 현금 연관도" 폐기 및 "신규 매수 여력(buy_readiness)" 재설계

Decision 4의 "평균 현금 연관도(`cash_relevance_avg`)"는 제품 의도에 맞지 않는다고
개발자가 확정했다. 이 지표를 폐기하고 "신규 매수 여력(buy_readiness)"으로 대체한다.

buy_readiness의 제품 의도는 관심 종목을 실제 매수 후보로 봐도 되는지, 현금이 부족해
관찰만 해야 하는지를 요약하는 지표다. 구성 요소는 두 가지다.

- **포트폴리오 현금 비중(`cash_weight`)**: `PortfolioService.get_summary(portfolio_id, user_id).cash_weight`로 산출한다. 현금이 충분할수록 매수 여력이 있다.
- **매수 검토 후보 수(`buy_candidate_count`)**: `SignalRepository.count_assets_with_active_signal(asset_ids, SignalType.BUY_CANDIDATE.value)`로 산출한다. 관심종목 내 `BUY_CANDIDATE` 활성 시그널 종목 수를 의미한다.

표현은 질적 레벨(`BuyReadinessLevel`)과 보조 수치를 포함한다. FE 카드 예시: "신규 매수 여력 / 제한적 / 현금 비중은 22.7%입니다. 매수 검토 후보는 5개지만, 현재는 분할 검토가 적합합니다."

**레벨 판정 규칙** (임계값 출처: `app/domains/portfolios/service.py:33-34`):

| 조건 | `BuyReadinessLevel` | 한국어 라벨 |
|---|---|---|
| `cash_weight >= CASH_FLOOR_MEDIUM` (≥ 0.15) | `SUFFICIENT` | 충분 |
| `CASH_FLOOR_HIGH <= cash_weight < CASH_FLOOR_MEDIUM` (0.05 ~ 0.15 미만) | `LIMITED` | 제한적 |
| `cash_weight < CASH_FLOOR_HIGH` (< 0.05) | `RESTRICTED` | 매우 제한적 |

포트폴리오가 등록되지 않은 경우 `buy_readiness`는 `null`로 반환한다.

#### R1-2. buy_readiness 배치: WatchlistSummaryResponse 확장 (Decision 5 역전)

R0 Decision 5는 두 집계 필드 모두 LLM 평가 결과에서 파생되므로
`WatchlistEvaluationsResponse`에 포함하고 `WatchlistSummaryResponse`를 변경하지 않기로 결정했다.

R1에서 이 결정을 역전한다. buy_readiness는 LLM 파생이 아니라 결정적 계산이 가능하므로,
summary의 빠른 DB 집계라는 성격을 깨지 않고도 `WatchlistSummaryResponse`에 포함할 수 있다.
구체적으로:
- `buy_candidate_count`는 순수 DB 집계(`SignalRepository.count_assets_with_active_signal`)다.
- `cash_weight`는 시장 데이터 조회가 필요하지만, LLM 호출과 달리 지연이 결정적이다.

두 값 모두 LLM에 의존하지 않으므로 summary 경계가 유지된다. `WatchlistEvaluationsResponse`에서
`cash_relevance_avg`를 제거하고, `WatchlistSummaryResponse`에 `buy_readiness` 필드를 추가한다.

#### R1-3. 포트폴리오 선택 방식

`GET /{watchlist_id}/summary` 엔드포인트에 선택적 쿼리 파라미터 `portfolio_id: int | None`을
추가한다. 파라미터가 제공되면 해당 포트폴리오를 사용하고, 제공되지 않으면
`PortfolioRepository.list_by_user(user_id, limit=1)`로 id 오름차순 첫 번째 포트폴리오를
사용한다. 포트폴리오가 없으면 `buy_readiness: null`을 반환한다.

`PortfolioService.get_summary`가 소유 확인(403)을 내부에서 처리하므로, `portfolio_id`가
지정된 경우 별도 소유 검증 없이 그대로 위임할 수 있다.

#### R1-4. Q1 반영: 분모 기준 및 LLM 누락 항목 처리 원칙

PR #236 리뷰 Q1에서 제기한 집계 분모 문제에 대해 개발자가 답변했다. 분모는 LLM 결과
항목 수가 아니라 snapshot(전체 관심종목 수) 기준이 원칙이다.

`cash_relevance_avg` 제거로 현재 비율 지표는 없다. `needs_research_count`는 비율이 아닌
절대 수이므로 분모 문제가 직접 적용되지 않는다.

LLM이 snapshot 항목을 누락했을 때의 처리 원칙은 다음과 같이 명시한다. `_project_items`는
snapshot 외 symbol을 필터링할 때 누락된 symbol(snapshot에 있지만 LLM 결과에 없는 symbol)
수를 warning 레벨로 로그에 기록한다. 이 처리는 서비스 레이어 집계 정확성을 추적할 수 있도록
한다.

#### R1-5. S1 반영: enum 외 값 항목 단위 스킵

PR #236 리뷰 S1에서 지적한 문제를 반영한다. LLM이 enum에 정의되지 않은 값을 반환할 때
`_project_items` 내 `_ValidatedEvaluation.model_validate` 호출이 `ValidationError`를 발생시켜
전체 요청이 500으로 실패한다.

변경 원칙: `_project_items`에서 `ValidationError`를 잡아 해당 항목만 스킵하고, 스킵된
symbol과 사유를 warning 레벨로 로그에 기록한다. 나머지 항목은 정상 처리한다. 전체 실패는
발생하지 않는다.

#### R1-6. S2 반영: mock.py 픽스처 enum 출처 주석

`app/adapters/llm/mock.py`의 `WatchlistEvaluationsResult` 픽스처(`"news_risk": "LOW"` 등)에
`# Enum values are sourced from app/domains/watchlists/types.py.` 주석을 추가한다.
`tests/test_watchlist_evaluations.py`에 이미 있는 주석과 일관성을 맞추기 위한 변경이다.

### 원본 결정 (R1 기준)

#### 1. 생성·캐싱 방식: 온디맨드 LLM 호출 + 게이트웨이 캐시

*변경 없음.* observations와 recommendations 선례를 그대로 따른다.
`LLMGateway.complete_json`이 이미 CLOUD 경로에서 `LLMResponseCache`를 통해 캐시 조회·저장을
처리하므로 서비스 레이어에서 별도 캐시 로직을 추가하지 않는다.

#### 2. 평가 4종 enum 정의

*변경 없음.* `app/domains/watchlists/types.py`의 enum 4종 정의는 그대로 유지한다.

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

#### 3. "추가 리서치 필요" 산출 기준

*변경 없음.* LLM 응답을 받은 뒤 서비스 레이어에서 다음 조건에 해당하는 종목을 집계한다.

```
news_risk == "HIGH" OR ai_judgment == "RISK_INCREASING"
```

#### 4. ~~"평균 현금 연관도" 산출 기준~~ (폐기)

R1-1에서 폐기됨. `cash_relevance_avg` 필드는 `WatchlistEvaluationsResponse`에서 제거한다.

#### 5. summary 필드 확장 위치 (R1에서 역전)

R0에서는 두 집계 필드를 `WatchlistEvaluationsResponse`에 포함하고 `WatchlistSummaryResponse`를
변경하지 않기로 했다. R1에서 이 결정을 역전한다. buy_readiness는 LLM 파생이 아니므로
`WatchlistSummaryResponse` 확장이 적합하다. 상세는 R1-2 참고.

#### 6. 엔드포인트 형태

*변경 없음.* `GET /api/v1/watchlists/{watchlist_id}/evaluations` child endpoint를 유지한다.
`GET /api/v1/watchlists/{watchlist_id}/summary`에는 R1-3에 따라 `portfolio_id` 쿼리 파라미터를 추가한다.

#### 7. ADR 필요 여부

*변경 없음.* 불필요.

## Interfaces

### `app/domains/watchlists/types.py` — BuyReadinessLevel 추가

```
class BuyReadinessLevel(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    LIMITED = "LIMITED"
    RESTRICTED = "RESTRICTED"
```

기존 `NewsRisk`, `ValuationBurden`, `ThemeHeat`, `AiJudgment` enum은 변경 없음.

### `app/domains/watchlists/schema.py` — WatchlistSummaryResponse 확장, WatchlistEvaluationsResponse 수정

신규 클래스:

```
class BuyReadinessProjection(BaseModel):
    level: str              # BuyReadinessLevel 값
    level_label: str        # 한국어 라벨 ("충분" | "제한적" | "매우 제한적")
    cash_weight: Decimal    # 현금 비중 (0.0–1.0)
    buy_candidate_count: int
    message: str            # FE 카드용 자연어 설명
```

`WatchlistSummaryResponse` 변경:

```
class WatchlistSummaryResponse(BaseModel):
    total_count: int
    risk_increasing_count: int
    recent_items: list[RecentWatchlistItemResponse]
    buy_readiness: BuyReadinessProjection | None   # 포트폴리오 없으면 None
```

`WatchlistEvaluationsResponse` 변경:

```
class WatchlistEvaluationsResponse(BaseModel):
    items: list[WatchlistItemEvaluationProjection]
    needs_research_count: int
    # cash_relevance_avg 제거 (R1-1)
    generated_at: UtcDatetime
```

### `app/domains/watchlists/service.py` — WatchlistService.get_summary 변경

`WatchlistService.__init__`에 `PortfolioRepository` 의존성 추가.

```
def get_summary(
    self,
    watchlist_id: int,
    user_id: int,
    portfolio_id: int | None = None,
    recent_limit: int = 5,
) -> WatchlistSummaryResponse
```

책임: 소유 확인, 기존 집계 3종, `buy_readiness` 계산.
`buy_readiness` 계산 순서: `portfolio_id` 또는 첫 번째 포트폴리오 조회 →
`PortfolioService.get_summary(resolved_portfolio_id, user_id).cash_weight` →
`count_assets_with_active_signal(asset_ids, SignalType.BUY_CANDIDATE.value)` →
레벨 판정(R1-1 기준) → `BuyReadinessProjection` 생성. 포트폴리오 없으면 `None`.

### `app/domains/watchlists/evaluations_service.py` — _project_items 방어 처리 변경

```
def _project_items(
    self,
    result_items: list[ItemEvaluationResult],
    snapshot_items: list[WatchlistEvaluationItem],
) -> list[_ValidatedEvaluation]
```

책임 변경: `ValidationError` 발생 시 해당 항목을 스킵하고 symbol과 오류를 warning 로그로 기록.
전체 실패 없이 유효한 항목만 반환한다.

### API 변경

`GET /api/v1/watchlists/{watchlist_id}/summary`에 선택적 쿼리 파라미터 추가:

```
GET /api/v1/watchlists/{watchlist_id}/summary
  Query params:
    recent_limit: int = 5 (기존)
    portfolio_id: int | None = None (신규)
  Response: ApiResponse[WatchlistSummaryResponse]
```

`GET /api/v1/watchlists/{watchlist_id}/evaluations` — 변경 없음 (응답 schema만 변경).

### `app/adapters/llm/mock.py` — 픽스처 주석 추가

`WatchlistEvaluationsResult` 픽스처 딕셔너리에 출처 주석 추가. 내용:
`# Enum values are sourced from app/domains/watchlists/types.py.`

## Dependencies

### 신규

- `app/domains/portfolios/repository` — `PortfolioRepository` (WatchlistService에 추가)
- `app/domains/portfolios/service` — `PortfolioService` (WatchlistService에서 get_summary 호출)

### 기존 (유지)

- `app/adapters/llm.gateway` — `LLMGateway.complete_json`
- `app/adapters/factory` — `get_llm_gateway()`
- `app/adapters/llm.privacy` — `CloudSafePayload`, `WatchlistEvaluationSnapshot`
- `app/domains/signals` — `SignalRepository.active_signal_types_by_asset`,
  `count_assets_with_active_signal`, `resolve_watchlist_status`
- `app/adapters/market` — `get_market_provider().get_quote`
- `app/domains/assets` — `AssetRepository`
- `app/domains/watchlists` — `WatchlistRepository`, `WatchlistItemRepository`

## Out of Scope

- 평가 결과 DB 저장·이력 관리
- 종목별 개별 뉴스 count snapshot 입력 (raw_news 도메인 확장 시 후속)
- FE 구현 (`project_stock_frontend#117` Phase 3)
- 평가 배치 사전 생성·스케줄러
- `BuyReadinessLevel` 판정 기준의 동적 설정화

## Test Strategy

### 신규·변경 테스트

- `WatchlistService.get_summary` — `buy_readiness` 포함 반환 (portfolio_id 제공·미제공 각각)
- `buy_readiness` 레벨 판정 경계값 테스트:
  - `cash_weight = 0.20` → `SUFFICIENT`
  - `cash_weight = 0.15` → `SUFFICIENT` (경계, 포함)
  - `cash_weight = 0.14` → `LIMITED`
  - `cash_weight = 0.05` → `LIMITED` (경계, 포함)
  - `cash_weight = 0.04` → `RESTRICTED`
- `buy_candidate_count` 집계 정확성 (활성 `BUY_CANDIDATE` 시그널 종목 수)
- 포트폴리오 없음 → `buy_readiness: null`
- `_project_items` enum 외 값 스킵: `ValidationError` 항목이 있어도 유효 항목이 정상 반환됨
- `WatchlistEvaluationsResponse`에 `cash_relevance_avg` 없음 확인
- 기존 `/observations`, `/recommendations`, `/summary`, `/sparklines` 테스트 약화·삭제 금지

### 변경된 픽스처

- `app/adapters/llm/mock.py`의 `WatchlistEvaluationsResult` 픽스처에 enum 출처 주석 추가
- 기존 evaluations 테스트의 `cash_relevance_avg` 검증 제거, `buy_readiness` 검증은 summary 테스트로 분리

## Open Questions

없음. R1에서 모든 open question이 해소됐다.
