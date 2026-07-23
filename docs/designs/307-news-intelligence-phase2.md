# BE 설계: 뉴스·공시 인텔리전스 2차 — 이슈 #307 (#306·#368·#369·#370)

상태: **계약 확정(Frozen)** — 2026-07-21. 에픽 BE #307, FE 에픽
`project_stock_frontend#198`. 1차 설계문서: `docs/designs/307-news-intelligence.md`.

이 문서는 2차 범위(이벤트 상세 #306, 투자자 동향 #368, 종목 민감도·키워드 관계망 #369,
이벤트 캘린더·에이전트 처리 현황 #370)를 스켈레톤 수준으로 확정한다. 테이블·enum·API 계약만
담고 쿼리·비즈니스 로직은 담지 않는다. 리터럴 출처는 사용자 제공 설계 지침(2026-07-14 확정 +
2026-07-21 보강, §3.5·§3.7·§3.8·§5.7·§5.8)과 1차 계약(`307-news-intelligence.md`)이다.
출처를 댈 수 없는 값은 "가정"으로 표기한다.

## 배경

1차는 `Document → Event → Topic → Insight → Evidence` 골격과 개요·피드·브리핑·토픽 맵·토픽
상세 계약을 고정했다. 2차는 그 위에 (a) 개별 이벤트 상세, (b) 투자자 수급 연결, (c) 종목 민감도와
토픽 내부 키워드 관계망, (d) 캘린더·처리 투명성 패널을 추가한다. 원칙은 1차와 동일하다: 사실과
AI 추론 분리, 근거 연결, 정량 숫자는 집계·LLM은 해석, 감성·중요도·영향도·연관 강도를 별도 필드로
유지. 2차도 실수집·실추출 전까지는 seed mock 위에서 계약을 고정한다.

와이어 컨벤션은 1차와 동일하다: snake_case, `UtcDatetime`, 점수 float(0~1), `ApiResponse`/
`success`/`cursor_paginated`, 인증 `get_current_user`. 금액(수급 net value)은 Decimal **문자열**로
표기한다(1차 점수와 구분).

## 1. Enum 추가 (types.py)

`SymbolRelationship`·`InvestorType`은 #305에서 이미 정의됨(2차 예고 → 2차 사용).

`MarketEventKind`: `EARNINGS`, `IR_EVENT`, `POLICY`, `RATE_DECISION`, `SHAREHOLDER_MEETING`,
`PRODUCT_EVENT`, `REGULATION`, `LOCKUP_EXPIRY`, `OTHER`. (출처: 스펙 §3.7)

`ValuationBurden`: `LOW`, `MEDIUM`, `HIGH`. (출처: 스펙 §5.8 밸류 부담. 표시용 라벨.)

`AgentStage`: `COLLECT`, `NORMALIZE`, `EXTRACT`, `CLUSTER`, `SENTIMENT`, `IMPACT`, `LINK`.
(출처: 스펙 §3.8·§6.7 Agent 역할 분리.)

`AgentRunStatus`: `RUNNING`, `COMPLETED`, `DELAYED`, `FAILED`. (가정 — 처리 현황 표시용.)

`FlowDirection`: `BUY`, `SELL`, `NEUTRAL`. (출처: 스펙 §3.5 순매수·순매도.)

## 2. 테이블 추가 (model.py) — 2차 4종

#306·#369(/graph)는 신규 테이블 없이 1차 모델(`extracted_events`·`event_evidence`·
`source_documents`·`keyword_relations`)을 재사용한다. 신규 테이블은 4종이다.

### 2.1 `investor_flows` (#368)

`id`, `market`(nullable), `topic_id`(FK topic_clusters, nullable — 시장 전체 vs 토픽 한정),
`investor_type`(InvestorType), `net_value`(Decimal — 금액, 문자열 직렬화), `direction`
(FlowDirection), `window`(집계 구간 라벨), `as_of`, `source_kind`(가정 — 유형별 수급 vs ETF·
거래량 대체 지표 구분: `INVESTOR_TYPE`/`ETF_FLOW`/`VOLUME_PROXY`), `created_at`. 인덱스:
`(topic_id, investor_type)`.

### 2.2 `topic_symbol_sensitivity` (#369 /symbols)

`id`, `topic_id`(FK topic_clusters), `symbol`, `exposure_score`(float, 실적·사업 직접 연결도),
`impact_direction`(SentimentDirection), `relationship`(SymbolRelationship), `valuation_burden`
(ValuationBurden, nullable), `note`(nullable), `created_at`. unique: `(topic_id, symbol)`.
**exposure_score와 impact_direction은 분리** — 노출도 높음 + 부정 조합 허용(스펙 §5.8).
`portfolio_weight`·`current_signal`은 저장하지 않고 조회 시 portfolios·signals 도메인에서 조인/
파생한다(중복 저장 회피).

### 2.3 `market_events` (#370 calendar)

`id`, `scheduled_at`, `event_kind`(MarketEventKind), `title`, `symbol`(nullable), `market`
(nullable), `importance_score`(float), `created_at`. 인덱스: `(scheduled_at)`. 토픽 연결은
`market_event_topics`(가정: id·market_event_id·topic_id) 조인 또는 `related_topic_ids` 파생.
1차 골격에서는 단순 `related_topic_ids`를 응답 계산으로 제공하고 조인 테이블은 필요 시 추가한다.

### 2.4 `agent_runs` (#370 agent-runs)

`id`, `started_at`, `finished_at`(nullable), `status`(AgentRunStatus), `processed_documents`
(int), `extracted_events`(int), `active_topics`(int), `analysis_version`, `created_at`.
스테이지별 상태는 `agent_run_stages`(가정: id·agent_run_id·stage(AgentStage)·status·delayed).
**검증 가능한 처리 단계·집계 수치만 저장** — 비공개 추론 과정은 저장·노출하지 않는다(스펙 §3.8).

마이그레이션: 단일 alembic revision(`create_news_insights_phase2_models`), 1차 head 위 스택.

## 3. API 계약 — 2차 (prefix `/api/v1/news-insights`)

### 3.1 `GET /events/{event_id}` — 이벤트 상세 (#306)

- 응답: `event_type`, `title`, `summary`, `importance`{score·level·explanation},
  `sentiment`{direction·score}, `affected_symbols`[{symbol·direction·exposure_score·reason}],
  `evidence`[{document_id·document_type·source·title·published_at·evidence_role}],
  `related_topics`[{topic_id·title}]. 존재하지 않는 event_id는 404.
- 신규 테이블 없음 — `extracted_events`·`event_evidence`·`source_documents` 재사용.

### 3.2 `GET /investor-flows` — 투자자 동향·반응 (#368)

- query: `market`·`window`·`topic_id`(optional). `window`는 저장된 집계 구간 라벨과
  일치시키는 값이 아니라, 서비스 기준 시각에서 과거로 조회할 기간이다. 조회 조건은
  `as_of >= 기준 시각 - window`다.
- 응답: `as_of`, `by_investor_type`[{investor_type·net_value(문자열)·direction·change}],
  `aggregation_windows`(실제 반환 행의 저장 집계 구간 라벨 목록, 데이터가 없으면 `null`),
  `narrative_alignment`{aligned(bool)·note}(뉴스 감성 vs 수급 방향 일치/불일치). 여러 집계
  구간의 행이 함께 반환되면 `aggregation_windows`는 중복을 제거하고 정렬해 모두 밝힌다.
  (스펙 §3.5·§5.7)
- 데이터 미제공 시장은 빈 값 추정 금지 — `availability`{available(bool)·fallback(ETF·거래량)}
  로 명시. 수급 숫자는 집계, LLM은 정렬 여부 해석만.

### 3.3 `GET /topics/{topic_id}/symbols` — 종목 민감도 (#369)

- 응답 item: `symbol`·`exposure_score`·`impact_direction`·`relationship`·`valuation_burden`·
  `portfolio_weight`(보유 시, portfolios 조인)·`current_signal`(signals 조인). (스펙 §5.8)
- **노출도(exposure_score)와 주가 방향(impact_direction) 분리.** `topic_symbol_sensitivity` 기반.

### 3.4 `GET /topics/{topic_id}/graph` — 키워드 관계망 (#369)

- 개요 토픽 맵(#303)보다 상세한 토픽 내부 관계망. query: 없음(topic 한정) 또는 `limit`.
- 응답: `nodes`[{id·label·type·mention_count·sentiment_score·related_event_ids·
  related_symbols}], `edges`[{source·target·strength·cooccurrence_count}]. (스펙 §5.5)
- 노드 클릭 필터링을 위해 `related_event_ids`·`related_symbols` 참조 포함. `keyword_relations`
  재사용. **연관 강도와 감성 분리.**

### 3.5 `GET /calendar` — 이벤트 타임라인 (#370)

- query: `window`(예 `5d`)·`market`·`topic_id`(optional).
- item: `scheduled_at`·`event_kind`·`title`·`symbol`·`market`·`importance`·`related_topic_ids`.
  (스펙 §3.7) `market_events` 기반.

### 3.6 `GET /agent-runs` — 에이전트 처리 현황 (#370)

- 최근 run 요약: `last_processed_at`·`processed_documents`·`extracted_events`·`active_topics`·
  `stages`[{name·status·delayed}]·`analysis_version`·`has_delay`(bool). (스펙 §3.8)
- **검증 가능한 처리 단계·집계 수치만** 반환. 비공개 추론 과정 노출 금지. `agent_runs`·
  `agent_run_stages` 기반.

## 4. 착수 순서 (2차)

1. #306 이벤트 상세 — 신규 테이블 없음, 1차 모델 재사용. 독립적이므로 선행.
2. 모델 추가(투자자·민감도·캘린더·에이전트 4종) + 마이그레이션 + seed — #368·#369·#370 공통 선행.
3. #368 투자자 동향 → #369 종목 민감도·키워드 관계망 → #370 캘린더·처리 현황.

모두 같은 도메인(라우터·schema·service 공유)을 수정하므로 **병렬 금지**, 순차 진행한다. 각 PR은
**base=dev**로 열고 브랜치만 스택한다(중간 브랜치 base 금지 — 스택 머지 함정 회피).

## 5. ADR·실패 기록 판단

- ADR: 신규 테이블·enum 추가이나 1차와 동일 아키텍처 패턴·와이어 컨벤션을 따르므로 **불요**.
  portfolios·signals 조인으로 파생하는 `portfolio_weight`·`current_signal`도 기존 도메인
  재사용이라 구조 변경이 아니다.
- 실패 기록: 해당 없음.
