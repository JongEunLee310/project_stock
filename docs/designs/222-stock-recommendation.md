# 222 · 종목 추천 API (Stock Recommendation)

Status: Implemented
작성: Claude Code (orchestrator via value-for-fable)
관련: BE #222, 설계 060(watchlist-observations), ADR-009(CloudSafe 경계)

## 1. 배경·목표

현재 사용자는 이미 관심 목록에 추가된 종목만 조회할 수 있습니다. 어떤 종목을 새로
추가하면 좋을지 알 수 없는 상태입니다.

이 설계는 특정 watchlist에 아직 포함되지 않은 등록 종목들을 후보로 구성하고,
각 후보의 공개 시장 지표(시그널 상태·PER·PEG·일간 변동률)를 컨텍스트로 LLM에 전달해
추천 종목 목록과 근거를 생성하는 엔드포인트를 정의합니다. 기존 `LLMGateway`,
`WatchlistHighlight`, `PrivacyGate` 등 이미 구현된 인프라를 재사용합니다.

## 2. 범위

포함:

- `LLMTaskType.STOCK_RECOMMENDATION` 추가 (`app/adapters/llm/types.py`·`router.py`).
- CloudSafe projection 타입 `StockRecommendationSnapshot` + 후보 항목
  `StockRecommendationCandidate` 및 빌더 `to_stock_recommendation_snapshot`
  (`app/adapters/llm/privacy.py`).
- LLM 출력 스키마 `RecommendationItem`·`StockRecommendationResult`
  (`app/adapters/llm/schema.py`).
- 시스템 프롬프트 상수 `STOCK_RECOMMENDATION_SYSTEM_PROMPT`
  (`app/adapters/llm/prompts/stock_recommendation.py`).
- API 응답 스키마 `StockRecommendationProjection`·`WatchlistRecommendationsResponse`
  (`app/domains/watchlists/schema.py`).
- 추천 생성 서비스 `WatchlistRecommendationsService`
  (`app/domains/watchlists/recommendations_service.py`).
- 엔드포인트 `GET /api/v1/watchlists/{watchlist_id}/recommendations`
  (`app/api/v1/endpoints/watchlists.py` 추가).
- `DEFAULT_MOCK_RESPONSES`에 `StockRecommendationResult` 결정적 응답 추가
  (`app/adapters/llm/mock.py`).

비포함:

- 추천 결과 영속화·이력 조회.
- 캐싱·예산 어댑터 신규 구현 — 기존 `LLMResponseCache`·`DailyCallBudget`은
  게이트웨이가 cloud 호출 시 자동 적용한다(`gateway.py` 행 105·123 기준).
- 후보 선정 규칙 고도화(외부 스크리너·재무 필터 등).
- FE 화면 — project_stock_frontend 별도 이슈.

## 3. API

### 3.1 엔드포인트

| Method | Path | 응답 | 비고 |
|--------|------|------|------|
| GET | `/api/v1/watchlists/{watchlist_id}/recommendations` | `WatchlistRecommendationsResponse` | on-demand 생성, 공통 `ApiResponse` 엔벨로프 |

- 인증: 기존 `get_current_user` 의존, 소유자 검증.
- 쿼리 파라미터: 없음(MVP).
- 에러: 미존재 404 (`WATCHLIST_NOT_FOUND`), 비소유 403 (`WATCHLIST_FORBIDDEN`).
  LLM 실패 시 예외 전파(safe template 폴백은 별도 ADR).

기존 watchlist 라우터(`watchlists.py`)에 라우트를 추가한다. 신규 라우터 파일은 불요
(observations 패턴과 동일).

### 3.2 응답 스키마

**`StockRecommendationProjection`** (위치: `app/domains/watchlists/schema.py`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `symbol` | `str` | 종목 코드 |
| `name` | `str` | 종목명 (`Asset.name` — `app/domains/assets/schema.py:17`) |
| `rationale` | `str` | LLM이 생성한 추천 근거 |
| `reference_metrics` | `list[str]` | LLM이 근거로 참조한 지표 요약 (가정 A) |

**`WatchlistRecommendationsResponse`** (위치: `app/domains/watchlists/schema.py`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `recommendations` | `list[StockRecommendationProjection]` | 추천 종목 목록 |
| `generated_at` | `UtcDatetime` | 생성 시각 (`app/core/schema.py`) |

API 응답: `ApiResponse[WatchlistRecommendationsResponse]` — 공통 envelope 준수
(`app/core/response.py`).

## 4. CloudSafe Projection

ADR-009에 따라 원본 asset entity는 클라우드로 보내지 않고, 화이트리스트 전용
projection만 전달합니다.

**`StockRecommendationCandidate`** (위치: `app/adapters/llm/privacy.py`)

| 필드 | 타입 | 출처 |
|------|------|------|
| `symbol` | `str` | `Asset.symbol` |
| `name` | `str` | `Asset.name` (공개 종목명) |
| `sector` | `str \| None` | `Asset.sector` |
| `status` | `str` | `resolve_watchlist_status` (`app/domains/signals/types.py`) |
| `per` | `Decimal \| None` | market provider quote |
| `peg` | `Decimal \| None` | market provider quote |
| `daily_change_percent` | `Decimal` | market provider quote |

`name`·`sector`는 공개 시장 정보이므로 AGGREGATED 등급 내에 포함됩니다.

**`StockRecommendationSnapshot(CloudSafePayload)`** (위치: `app/adapters/llm/privacy.py`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `sensitivity` | `ClassVar[SensitivityLevel]` | `AGGREGATED` |
| `watchlist_id` | `int` | 대상 watchlist 식별자 |
| `current_symbols` | `list[str]` | 현재 watchlist에 있는 종목 코드 (LLM이 중복 추천을 피하기 위한 맥락) |
| `candidate_count` | `int` | 전달된 후보 종목 수 |
| `candidates` | `list[StockRecommendationCandidate]` | 후보 종목 공개 지표 |

빌더 시그니처 (위치: `app/adapters/llm/privacy.py`):

```
def to_stock_recommendation_snapshot(
    watchlist_id: int,
    current_symbols: list[str],
    candidates: list[StockRecommendationCandidate],
) -> StockRecommendationSnapshot
```

책임: watchlist 식별자, 현재 보유 심볼 목록, 후보 항목을 받아 projection을 구성합니다.
cap·해소는 서비스가 빌더 호출 전에 완료합니다.

### 4.1 프라이버시 판단 (ADR-009)

- `symbol`·`name`·`sector`는 공개 종목 정보입니다.
- `status`는 signals 도메인이 계산한 활성 신호 종류(공개 지표 기반)로, observations
  설계 060 §3.1에서 정렬한 trade-off와 동일합니다.
- `current_symbols`는 "이 사용자가 해당 종목을 관심 목록에 두고 있다"는 사실을 노출하며,
  이는 060 §3.1의 observations payload가 이미 허용한 범위와 동일합니다.
- 보유 수량·평가액은 포함되지 않습니다.
- payload 등급은 `AGGREGATED`이고 `PrivacyGate.guard`를 통과합니다.
- 후보 수 상한(`RECOMMENDATION_CANDIDATE_LIMIT`, 가정 B)으로 단일 cloud 호출 payload를
  bounding합니다.

## 5. LLM 스키마

**`RecommendationItem`** (위치: `app/adapters/llm/schema.py`)

| 필드 | 타입 |
|------|------|
| `symbol` | `str` |
| `rationale` | `str` |
| `reference_metrics` | `list[str]` |

**`StockRecommendationResult`** (위치: `app/adapters/llm/schema.py`)

| 필드 | 타입 |
|------|------|
| `recommendations` | `list[RecommendationItem]` |

LLM은 `candidates` 중에서 추천할 종목을 선택하며, `symbol`은 반드시 `candidates`에
있는 값이어야 합니다. 서비스는 LLM이 반환한 각 `symbol`을 후보 목록과 교차 검증하고,
후보에 없는 심볼은 필터링합니다.

## 6. LLM 프롬프트 책임 분리

| 주체 | 역할 |
|------|------|
| 코드 (서비스) | 후보 종목 선정(등록 종목 중 watchlist 미포함 active 종목), cap 적용, 시그널·PER·PEG·일간변화 해소, `StockRecommendationSnapshot` 구성, LLM 반환 symbol 교차 검증 및 필터링, `name` 조회(Asset DB) |
| LLM | 후보 중 추천 종목 선택, 추천 근거(`rationale`) 생성, 참조 지표(`reference_metrics`) 요약 |

프롬프트 모듈은 시스템 프롬프트 문자열 상수만 제공합니다. 게이트웨이가 projection을
user 메시지로 직렬화하므로 프롬프트 모듈에 직렬화 로직은 없습니다. 기존
`watchlist_observation.py`·`dashboard_briefing.py`와 동일한 구조입니다.

## 7. 새 LLMTaskType 등록

`LLMTaskType.STOCK_RECOMMENDATION` 을 `app/adapters/llm/types.py` enum에 추가하고,
`LLM_TASK_ROUTES`(`app/adapters/llm/router.py`)에 등록합니다.

가정 C: `TaskRoute(launch="cloud", future_primary="local")` — `WATCHLIST_NOTE`·
`DASHBOARD_BRIEFING`과 동일한 전략.

## 8. Service·Repository 시그니처

### WatchlistRecommendationsService

위치: `app/domains/watchlists/recommendations_service.py`

```
class WatchlistRecommendationsService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None

    def generate(
        self,
        watchlist_id: int,
        user_id: int,
    ) -> WatchlistRecommendationsResponse
```

`generate` 처리 순서:

1. `_get_owned_watchlist` 관례로 소유권을 검증합니다(미존재 404 `WATCHLIST_NOT_FOUND`,
   비소유 403 `WATCHLIST_FORBIDDEN`).
2. `WatchlistItemRepository.list_by_watchlist(watchlist_id)` + `AssetRepository.list_by_ids`
   로 현재 watchlist의 asset_id 집합을 구합니다.
3. `AssetRepository.list_all(is_active=True)`로 전체 활성 종목을 가져온 뒤 현재
   watchlist에 이미 포함된 종목을 제외합니다.
4. 후보 집합을 상위 `RECOMMENDATION_CANDIDATE_LIMIT`(가정 B)개로 제한합니다.
5. 각 후보의 `symbol`·sector·status·PER·PEG·일간변화를 해소해
   `StockRecommendationCandidate` 리스트를 만듭니다.
   해소 경로는 `active_signal_types_by_asset` + `resolve_watchlist_status` +
   market provider quote로, observations 서비스와 동일합니다.
6. `to_stock_recommendation_snapshot(watchlist_id, current_symbols, candidates)` 로
   `StockRecommendationSnapshot`을 구성합니다.
7. `gateway.complete_json(LLMTaskType.STOCK_RECOMMENDATION, snapshot,
   StockRecommendationResult, STOCK_RECOMMENDATION_SYSTEM_PROMPT)` 를 호출하고
   `StockRecommendationResult.model_validate(...)` 로 구조화합니다.
8. LLM이 반환한 각 `symbol`을 후보 목록과 교차 검증하고 후보에 없는 항목은
   제거합니다.
9. 검증된 심볼을 기반으로 `Asset.name`을 조회(`AssetRepository.list_by_ids` 또는
   후보 목록 캐시 활용)해 `StockRecommendationProjection`을 구성합니다.
10. `WatchlistRecommendationsResponse(recommendations=..., generated_at=utc_now())`를
    반환합니다.

결과는 영속화하지 않습니다. 빈 후보 목록(모든 active 종목이 이미 watchlist에 있는 경우)은
빈 `recommendations`를 반환합니다.

### Repository 변경

신규 repository 메서드 불요. 기존 메서드 재사용:

| 메서드 | 위치 | 용도 |
|--------|------|------|
| `WatchlistRepository.get_by_id` | `watchlists/repository.py` | 소유권 검증 |
| `WatchlistItemRepository.list_by_watchlist` | `watchlists/repository.py` | 현재 watchlist 항목 조회 |
| `AssetRepository.list_all(is_active=True)` | `assets/repository.py` | 전체 활성 종목 조회 |
| `AssetRepository.list_by_ids` | `assets/repository.py` | 후보 asset 상세 조회 |
| `SignalRepository.active_signal_types_by_asset` | `signals/repository.py` | 시그널 상태 해소 |

## 9. Mock 동작 정의

`app/adapters/llm/mock.py` `DEFAULT_MOCK_RESPONSES`에 `"StockRecommendationResult"` 키로
항목을 추가합니다. `MockLLMClient.complete_json`은 `schema.__name__` 을 키로 조회합니다
(`mock.py:67` 기준).

결정적 mock 응답 형태:

```python
"StockRecommendationResult": {
    "recommendations": [
        {
            "symbol": "AAPL",
            "rationale": "Mock recommendation rationale.",
            "reference_metrics": ["Mock metric A", "Mock metric B"],
        }
    ]
}
```

`symbol` 값 `"AAPL"` 은 가정 D입니다. 실제 테스트 픽스처는 구현 시
`AssetRepository`에 등록된 실제 active 종목 심볼을 확인해 작성해야 합니다(Real-Contract
Fixtures 규율).

## 10. 캐시·예산 어댑터 재사용

`LLMResponseCache`와 `DailyCallBudget` 은 `gateway.complete_json`이 cloud 호출 시
자동으로 적용합니다(`gateway.py` 행 105·123). 서비스는 직접 호출하지 않습니다.
observations(060) 패턴과 동일하며, 별도 설정 변경은 불요합니다.

## 11. DB 변경

신규 테이블 없음. on-demand 생성이며 결과를 영속화하지 않습니다.

## 12. 의존 도메인

- `app/adapters/llm/gateway.py` — `LLMGateway.complete_json` 재사용.
- `app/adapters/llm/types.py` — `LLMTaskType.STOCK_RECOMMENDATION` 신규 추가.
- `app/adapters/llm/router.py` — `LLM_TASK_ROUTES`에 `STOCK_RECOMMENDATION` 신규 등록.
- `app/adapters/llm/privacy.py` — `StockRecommendationCandidate`·`StockRecommendationSnapshot`·
  `to_stock_recommendation_snapshot` 신규 추가.
- `app/adapters/llm/schema.py` — `RecommendationItem`·`StockRecommendationResult` 신규 추가.
- `app/adapters/llm/mock.py` — `DEFAULT_MOCK_RESPONSES`에 `StockRecommendationResult` 추가.
- `app/adapters/factory.py` — `get_llm_gateway` 재사용(서비스 조립).
- `app/domains/watchlists` (repository·service·model) — 소유권·항목 조회 재사용.
- `app/domains/assets/repository.py` — 활성 종목 목록·상세 조회.
- `app/domains/signals/repository.py` — `active_signal_types_by_asset` 재사용.
- `app/domains/signals/types.py` — `resolve_watchlist_status` 재사용.
- `app/domains/signals/time.py` — `utc_now` 재사용.
- market provider (`app/adapters/factory.py` `get_market_provider`) — quote 해소.
- `app/core/schema.py` (`UtcDatetime`)·`app/core/response.py` (`ApiResponse`·`success`)
  재사용.

## 13. 가정 (Assumption)

구현 전 생산자 코드 또는 런타임에서 검증이 필요한 리터럴과 계약을 명시합니다.

| ID | 항목 | 가정 값 | 검증 방법 |
|----|------|---------|-----------|
| A | `StockRecommendationResult.recommendations[].reference_metrics` 타입 | `list[str]` (자유 텍스트) | FE 계약 확정 후 구조화 여부 재검토 |
| B | `RECOMMENDATION_CANDIDATE_LIMIT` 후보 수 상한 | `20` | ADR-009 §3.1 payload bounding 논리로 검토 (observations의 30개 대비 추천 맥락은 더 많은 항목이 필요할 수 있음) |
| C | `LLM_TASK_ROUTES["STOCK_RECOMMENDATION"]` 값 | `TaskRoute(launch="cloud", future_primary="local")` | `router.py` 신규 등록 시 결정 |
| D | mock 응답의 `symbol` 값 | `"AAPL"` | 구현 시 실제 등록된 active 종목으로 교체 (Real-Contract Fixtures 규율) |
| E | LLM이 반환하는 추천 종목 수 상한 | 명시적 제한 없음 (프롬프트 지시로만 관리) | 구현 시 `StockRecommendationResult` Pydantic 검증 또는 프롬프트 강제 여부 결정 |

## 14. 열린 질문

1. **후보 상한(B)**: `RECOMMENDATION_CANDIDATE_LIMIT` 를 20으로 설정할 때 cloud 호출
   payload 크기가 허용 범위 내인지 — active 종목 총수가 증가할 경우 상한 조정 필요.

2. **후보 선정 정렬 기준**: `AssetRepository.list_all(is_active=True)` 결과를 `id` 순으로
   자르는 것 외에, 시그널이 활성인 종목을 우선 노출하는 정렬이 추천 품질을 높이는지.

3. **추천 종목 수 상한(E)**: LLM이 반환하는 최대 추천 수를 프롬프트 지시로만 관리할지,
   아니면 `StockRecommendationResult` 스키마 또는 서비스에서 강제 cap을 둘지.

4. **`reference_metrics` 구조화(A)**: 현재 `list[str]` 자유 텍스트로 정의하나, FE가 특정
   필드(예: PER 값, 신호 유형)를 구조화 형태로 소비할 가능성 — FE 이슈 확정 후 재검토.

5. **에스컬레이션 정책**: `STOCK_RECOMMENDATION` 에 `EscalationPolicy` 를 적용할지 — 현재
   `WATCHLIST_NOTE` 등도 에스컬레이션 없이 단순 cloud 라우팅이므로 동일 패턴 유지가
   기본안.
