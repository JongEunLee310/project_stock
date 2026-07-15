# Design: research-summary 실생성 전환 — 저장·생성·재생성 (#322)

- Status: Accepted
- Issue: #322
- 선행 인프라: `LLMGateway`(ADR-007/010/011/012), CloudSafe projection(ADR-009), `LLMTaskType` 라우팅(ADR-008)

## 1. 배경

리서치 상세의 AI briefing은 현재 `ResearchSummaryService.get_summary`가 하드코딩
템플릿 2종을 `asset.id % 2`로 돌려주는 mock이며, `created_at`도 고정 상수
(2026-06-19 UTC)입니다. LLM 인프라(`LLMGateway`·`ContextBuilder`·일일 호출 상한
가드)와 응답 계약 구조화(#267, #298)는 이미 갖춰져 있어, 생성·저장 경로를
연결하는 작업만 남았습니다.

## 2. 코드 근거 조사 (실측, 파일:행)

| 확인 사항 | 근거 | 설계 반영 |
| --- | --- | --- |
| 현재 mock 로직 | `service.py:186` `_SUMMARY_TEMPLATES[asset.id % len(...)]`, `service.py:15` `_CREATED_AT` 상수 | 제거 대상 |
| 일일 호출 상한 가드의 실제 위치 | `gateway.py:123-124` — `complete_json`이 provider가 cloud로 해석될 때 `self.call_budget.consume()`을 내부에서 자동 호출. 별도 가드 API를 서비스에서 직접 부를 필요가 없다 | `LLM_TASK_ROUTES`에 `RESEARCH_SUMMARY`를 cloud로 등록하면 가드가 자동 적용됨 |
| 라우트 미등록 시 동작 | `router.py:41-45` `LLMRouter.resolve`는 라우트가 없으면 `LLMRoutingError` | `LLM_TASK_ROUTES`에 `RESEARCH_SUMMARY` 항목 필수 추가 |
| 예산 초과 시 HTTP 응답 | `LLMBudgetExceededError`(`exceptions.py:17`)를 캐치하는 도메인 코드가 없음(grep 확인). `STOCK_RECOMMENDATION` 경로(`recommendations_service.py`)도 별도 처리 없이 전파시키며, `app/core/exceptions.py:30-33`의 `unhandled_exception_handler`(일반 `Exception` 핸들러)로 흘러가 비구분 500이 된다 | **가정**: 이번 범위는 기존 관례(비구분 500)를 그대로 따른다. 전용 4xx 매핑이 필요하면 별도 결정 사항으로 분리 — 구현 전 확인 필요 |
| `build_symbol_context`의 포트폴리오 결합 | `context_builder.py:76-101, 163-188` — `user_id`가 필수 인자이며, 보유 시 `portfolio_context`를 채운다. "제외 전용" 오버로드는 코드에 없음 | 스냅샷 매핑 단계에서 `portfolio_context` 필드를 아예 옮기지 않는 방식으로 배제한다 (호출 자체는 `build_symbol_context`를 그대로 사용) |
| research_queue의 소비 방식 | `research_queue/service.py:70` `summary = self.summary_service.get_summary(asset.id)`를 모든 활성 자산에 무조건 호출. `get_summary`가 404를 던지도록 바뀌면 저장본 없는 자산에서 큐 조회 자체가 깨진다 | strict 조회와 별도로 저장본 부재 시 `None`을 반환하는 조회 메서드가 필요 |
| research_queue projection의 nullable 계약 | `research_queue/schema.py:33-34` `stance: str \| None`, `headline: str \| None` — 이미 nullable | 스키마 변경 없이 서비스 레이어에서만 fallback 처리 |
| 신규 테이블 패턴 전례 | `valuation/model.py`(`ValuationSnapshot`) — `UniqueConstraint` + `TimestampMixin`. `valuation/repository.py:14-44` — select 후 없으면 insert·있으면 필드 갱신하는 upsert(ORM flush로 `updated_at`이 `onupdate=func.now()`에 의해 매 갱신마다 자동 반영됨). `decision_checklist/model.py`(`BuyChecklistNote`) — 자산 단위 unique 행 + JSON 컬럼(`checked_item_keys`) 전례 | 동일 패턴을 `research_summaries`에 적용 |
| 신규 에러코드 등록 위치 | `app/core/error_codes.py:12-32` — `ASSET_NOT_FOUND` 등 `*_NOT_FOUND` enum 값이 나열된 자리 | `RESEARCH_SUMMARY_NOT_FOUND` 추가 |
| mock provider 기본 응답 등록 위치 | `app/adapters/llm/mock.py:8` `DEFAULT_MOCK_RESPONSES` dict, 결과 타입명을 키로 사용(`"BriefingResult"`, `"WatchlistEvaluationsResult"` 등, #203 전례) | `"ResearchSummaryResult"` 키 추가 |
| 한국어 출력 지시 전례 | `app/adapters/llm/prompts/stock_recommendation.py` — 시스템 프롬프트 뒤에 `KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION`을 붙이는 패턴 | 동일 패턴 재사용 |
| LLM 결과 스키마 등록 위치 | `app/adapters/llm/schema.py` — `StockRecommendationResult` 등 Result 클래스가 모여 있는 파일 | `ResearchSummaryResult` 추가 |

`portfolio_context` 배제와 관련해, `build_symbol_context`에 넘기는 `user_id`는
저장 결과(`research_summaries`)에는 영향을 주지 않고 내부 조회에만 쓰인 뒤
버려진다. 자산 단위로 1행만 저장하는 계약이므로 트리거한 사용자에 따라 결과가
달라지지 않아야 한다는 점을 구현 시 유지해야 한다.

## 3. 계약

### 3.1 테이블: `research_summaries`

| 컬럼 | 타입 | 제약 | 의미 |
| --- | --- | --- | --- |
| `id` | int | PK | |
| `asset_id` | int | FK `assets.id`, `UniqueConstraint("asset_id", name="uq_research_summaries_asset")` | 자산별 최신 1행만 유지 |
| `stance` | str | not null | `ResearchSummaryResponse.stance` |
| `stance_confidence` | str | not null | `ResearchSummaryResponse.stance_confidence` |
| `stance_comment` | str | nullable | |
| `headline` | str | not null | |
| `body` | Text | not null | |
| `positive_factors` | JSON | default `[]` | `list[str]` |
| `caution_factors` | JSON | default `[]` | `list[str]` |
| `next_checks` | JSON | default `[]` | `list[str]` |
| `counter_points` | JSON | default `[]` | `CounterPoint` 구조 리스트(직렬화) |
| `confidence_basis` | str | nullable | |
| `key_risks` | JSON | not null | `ResearchRisk` 구조 리스트(직렬화) |
| `created_at` / `updated_at` | DateTime(tz) | `TimestampMixin` | `updated_at`이 매 재생성 upsert마다 갱신되며, 이것이 응답의 실제 생성 시각 소스가 된다 |

응답 스키마 `ResearchSummaryResponse.created_at` 필드명은 기존 계약과의 호환을
위해 그대로 유지하되, 값의 출처는 저장 행의 `updated_at`(마지막 생성 시각)으로
바뀐다. 이 이름-의미 불일치는 의도된 것이며 핸드오프에서 주석으로 명시한다.

### 3.2 `LLMTaskType.RESEARCH_SUMMARY`

- `app/adapters/llm/types.py`의 `LLMTaskType` enum에 값 추가.
- `app/adapters/llm/router.py`의 `LLM_TASK_ROUTES`에 `TaskRoute(launch="cloud", future_primary="local")` 추가 — **가정**: `STOCK_RECOMMENDATION`과 동일하게 신규 생성형 카드 태스크로 분류. 로컬 모델 성숙도에 따라 향후 조정 가능.
- 한국어 출력 프롬프트: `app/adapters/llm/prompts/research_summary.py`에 `RESEARCH_SUMMARY_SYSTEM_PROMPT` 신설, `stock_recommendation.py` 패턴을 따른다.
- 결과 스키마: `app/adapters/llm/schema.py`에 `ResearchSummaryResult` 추가 — `ResearchSummaryResponse`에서 `asset_id`·`created_at`을 뺀 구조(생성 시점에 서비스가 채움).
- mock 기본 응답: `app/adapters/llm/mock.py`의 `DEFAULT_MOCK_RESPONSES["ResearchSummaryResult"]`에 결정적 항목 추가.

### 3.3 CloudSafe 스냅샷

- `app/adapters/llm/privacy.py`에 `ResearchSummarySnapshot(CloudSafePayload)` 추가 — `sensitivity = SensitivityLevel.AGGREGATED`.
- 필드: `symbol`, `market`, `display_name`, `price_snapshot`(`ContextBundlePriceSnapshotProjection` 재사용), `recent_news`(`ContextBundleRecentNewsProjection` 재사용), `signals`(`ContextBundleSignalProjection` 재사용). `portfolio_context`는 필드 자체를 두지 않아 배제한다.
- 매핑 함수 `to_research_summary_snapshot(card: SymbolCard) -> ResearchSummarySnapshot` — `SymbolCard`에서 위 필드만 옮기고 `portfolio_context`는 사용하지 않는다.

### 3.4 API

| 메서드 | 경로 | 요청 | 응답 | 비고 |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/assets/{asset_id}/research-summary` | path `asset_id` | `ResearchSummaryResponse` | 저장본 없으면 `404 RESEARCH_SUMMARY_NOT_FOUND` |
| `POST` | `/api/v1/assets/{asset_id}/research-summary/refresh` | path `asset_id` | `ResearchSummaryResponse` | 생성·저장 트리거, 일일 상한 초과 시 기존 관례대로 500 전파(§2 표 참고) |

두 엔드포인트 모두 `Auth: Required`(기존 GET과 동일), `자산 없음 → 404 ASSET_NOT_FOUND`.

## 4. 구현 스켈레톤

- `app/domains/research_summary/model.py` (신설) — `ResearchSummaryRow(Base, TimestampMixin)`: §3.1 컬럼.
- `app/domains/research_summary/repository.py` (신설):
  - `get_by_asset_id(asset_id: int) -> ResearchSummaryRow | None` — 저장본 조회.
  - `upsert(asset_id: int, result: ResearchSummaryResult) -> ResearchSummaryRow` — `ValuationRepository.upsert` 패턴(select 후 insert-or-update, `self.db.commit()`/`self.db.refresh`).
- `app/domains/research_summary/schema.py` — 기존 `ResearchSummaryResponse`/`CounterPoint`/`ResearchRisk` 그대로 유지. 저장 행 → 응답 변환은 서비스에서 처리.
- `app/domains/research_summary/service.py`:
  - `ResearchSummaryService.__init__(self, db: Session, gateway: LLMGateway, context_builder: ContextBuilder | None = None)` — 책임: 저장소·LLM 게이트웨이·컨텍스트 빌더 의존성 보관.
  - `get_summary(self, asset_id: int) -> ResearchSummaryResponse` — 책임: GET 엔드포인트용 strict 조회, 자산 없음 404 `ASSET_NOT_FOUND`, 저장본 없음 404 `RESEARCH_SUMMARY_NOT_FOUND`.
  - `get_summary_or_none(self, asset_id: int) -> ResearchSummaryResponse | None` — 책임: research_queue fallback용 non-strict 조회, 저장본 없으면 `None`.
  - `generate(self, asset_id: int, user_id: int) -> ResearchSummaryResponse` — 책임: 자산 검증 → `context_builder.build_symbol_context(user_id, asset.symbol, asset.market)` 호출 → `to_research_summary_snapshot`으로 변환(포트폴리오 컨텍스트 배제) → `gateway.complete_json(LLMTaskType.RESEARCH_SUMMARY, snapshot, ResearchSummaryResult, RESEARCH_SUMMARY_SYSTEM_PROMPT)` → 결과 검증 → `repository.upsert` → 저장 행을 `ResearchSummaryResponse`로 변환해 반환.
  - `_SUMMARY_TEMPLATES`, `_CREATED_AT`, `_RiskTemplate`, `_CounterPointTemplate`, `_SummaryTemplate` 전부 제거.
- `app/api/v1/endpoints/assets.py`:
  - 기존 `GET /{asset_id}/research-summary`는 `ResearchSummaryService(db, get_llm_gateway()).get_summary(asset_id)` 호출로 변경(현재 135행 근처).
  - `POST /{asset_id}/research-summary/refresh` 신설 — `ResearchSummaryService(db, get_llm_gateway()).generate(asset_id, current_user.id)`, `analyst-opinions`·`recommendations` 엔드포인트 등록 관례를 따른다.
- `app/domains/research_queue/service.py`:
  - `list_queue`의 `summary = self.summary_service.get_summary(asset.id)`(70행)를 `self.summary_service.get_summary_or_none(asset.id)`로 교체.
  - `summary`가 `None`이면 `stance=None`, `headline=None`으로 `ResearchQueueItemProjection`을 구성(스키마는 이미 nullable).
- Alembic migration — `research_summaries` 테이블 생성, `alembic/versions/` 최신 리비전 뒤에 연결.
- `docs/api/frontend-api-spec.md` — GET 섹션(387행 근처)에 "저장본 없으면 404" 설명 갱신, POST refresh 섹션 신설, 138·149행 근처 개요 표의 "Mock 요약" 주석 제거.
- `tests/test_api_contract.py` — 727행 근처 `test_research_summary_response_contract`를 저장본 기반으로 갱신(사전에 refresh 또는 직접 upsert로 저장본을 만든 뒤 조회), 저장본 없음 404 케이스 추가, refresh 엔드포인트 계약 테스트 추가.

## 5. Test / Verification

- 계약 테스트: GET 저장본 반환, 저장본 없음 404 `RESEARCH_SUMMARY_NOT_FOUND`, POST refresh 응답 형태.
- 서비스 테스트: `generate`가 CloudSafe 스냅샷에 `portfolio_context`를 포함하지 않는지, upsert가 동일 asset_id에서 행을 늘리지 않고 갱신만 하는지.
- research_queue 회귀 테스트: 저장본 없는 자산에서 큐 조회가 예외 없이 `stance=None`/`headline=None`으로 응답하는지.
- mock provider 결정성: `DEFAULT_MOCK_RESPONSES["ResearchSummaryResult"]` 고정 값 검증.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` / `uv run alembic heads`

## 6. Out of Scope

- FE 상태 처리·재생성 UI (JongEunLee310/project_stock_frontend#219, BE 머지 후 진행).
- 요약 이력 보관 — 최신 1행만 유지.
- 주기 잡에 의한 자동 재생성 — #209 정책(주기 잡 LLM 금지) 유지.
- 예산 초과 시 전용 4xx 응답 매핑 — 기존 관례(비구분 500) 유지, 별도 결정 필요 시 후속.
