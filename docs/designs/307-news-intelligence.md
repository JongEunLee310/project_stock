# BE 설계: 뉴스·공시 인텔리전스 파이프라인 1차 — 이슈 #307 (모델 #305 · 계약 #301~#304)

상태: **계약 확정(Frozen)** — 2026-07-21. 에픽 BE #307, FE 에픽
`project_stock_frontend#198`.

이 문서는 1차 MVP 범위(데이터 모델 골격 #305 + 개요·피드·브리핑·토픽 맵·토픽 상세 계약
#301~#304)를 스켈레톤 수준으로 확정한다. 테이블·enum·API 계약만 담고 쿼리·비즈니스 로직은
담지 않는다. 리터럴(enum 값·필드 형식)의 출처는 사용자 제공 설계 지침(2026-07-14 확정 +
2026-07-21 보강)과 기존 계약(`docs/designs/268-news-disclosure-metadata.md`, `app/core`
와이어 컨벤션)이다. 출처를 댈 수 없는 값은 "가정"으로 표기한다.

## 배경

기존 `news`·`raw_news`·`ingestion` 도메인은 원문 뉴스 수집·정규화를 담당한다. 이 파이프라인은
그 위에 `Document → Event → Topic → Insight → Evidence` 분석 계층을 올린다. 목표는 사용자가
모든 기사를 읽지 않아도 "지금 무엇이 중요해졌는가"를 파악하게 하는 것이다.

핵심 원칙(에픽 #307과 공유):

1. **문서와 이벤트를 구분한다** — 같은 사건의 기사 N건은 이벤트 1건 + evidence N개로 병합.
2. **사실과 AI 추론을 분리한다** — documents·events(사실)와 topics·insights(추론)를 별도 테이블로.
3. **모든 AI 결과에 근거를 연결한다** — 브리핑 문장·인사이트는 존재하는 event ID만 참조.
4. **분석을 덮어쓰지 않는다** — `topic_insights`는 버전 누적.

1차는 **mock 데이터로 계약·모델을 먼저 고정**하고, 실수집·실추출 파이프라인(임베딩 클러스터링·
LLM 추출)은 후속으로 둔다. 기존 `GET /assets/{id}/news-disclosure` 계약은 변경하지 않는다.

## 와이어 컨벤션 (기존 계약 계승)

- 필드: snake_case. 시각: `app/core/schema.py`의 `UtcDatetime`(`...Z`).
- 점수(score) 필드: 0.0~1.0 범위 `float`. 금액(2차 수급 등): Decimal **문자열** (1차 범위 밖).
- 공통 엔벨로프: `app/core/response.py`의 `ApiResponse`/`success`/`paginated`.
- 피드 페이지네이션: **cursor 기반**(신규 유입 시 offset 중복·누락 방지). `app/core/pagination.py` 확장.
- enum 정본: 영문 UPPER_SNAKE. FE 표시 계층에서 한글화. 잘못된 값은 입력 검증 422.

## 1. 도메인 배치

기존 도메인 패턴(`model` / `types` / `schema` / `repository` / `service` + router)을 따른다.

```text
app/domains/news_insights/
  model.py        # 7개 ORM 모델 (1차)
  types.py        # enum 정의
  schema.py       # 요청·응답 Pydantic 모델
  repository.py   # 영속성 접근
  service.py      # 유스케이스 (overview BFF·events·topics)
  briefing.py     # 브리핑 조립·근거 검증 (#302)
  seed.py         # mock seed 헬퍼 (1차 계약 시연용)
app/api/v1/endpoints/news_insights.py  # 라우터 (prefix /api/v1/news-insights)
```

## 2. Enum (types.py) — 정본 영문 UPPER_SNAKE

`DocumentType`: `NEWS`, `DISCLOSURE`, `EARNINGS`, `ANALYST_REPORT`, `COMMUNITY`,
`COMPANY_IR`. (출처: #305)

`ProcessingStatus`: `PENDING`, `NORMALIZED`, `EXTRACTED`, `FAILED`. (가정 — 문서 처리
라이프사이클용, 지침에 status 존재만 명시.)

`EventType`(초기 집합, 확장형): `EARNINGS_GUIDANCE`, `BUYBACK`, `REGULATION`,
`SUPPLY_CONTRACT`, `MANAGEMENT_CHANGE`, `ACCOUNTING_ISSUE`, `PRODUCTION_DISRUPTION`,
`OTHER`. (출처: 스펙 §3.1 고중요 이벤트 예시. `OTHER`로 확장 허용.)

`SentimentDirection`: `POSITIVE`, `NEUTRAL`, `NEGATIVE`, `MIXED`. (출처: 스펙 피드 컬럼 §3.2)

`ImportanceLevel`: `LOW`, `MEDIUM`, `HIGH`. (importance_score를 구간화한 표시용 라벨.)

`EvidenceRole`: `PRIMARY`, `SUPPORTING`, `CONTRADICTING`, `BACKGROUND`. (출처: 스펙 §5.6)

`LifecycleStatus`: `EMERGING`, `RISING`, `ACTIVE`, `COOLING`, `ARCHIVED`. (출처: 스펙 §5.1)

`EventStatus`: `ACTIVE`, `MERGED`, `DISMISSED`. (가정 — 사건 병합·폐기 처리용.)

`TopicCategory`: `GROWTH`, `REGULATION`, `EARNINGS`, `DEMAND`, `MARKET_EVENT`,
`CAPITAL_POLICY`, `SUPPLY_CHAIN`. (출처: 개요 토픽 맵 범례 §3.4 — 성장/투자·규제/정책·
실적/기업·수요/소비·시장 이벤트·자본정책.)

2차 예고(정의만, 1차 미사용): `SymbolRelationship`(`DIRECT`·`SUPPLY_CHAIN`·`COMPETITOR`·
`CUSTOMER`), `InvestorType`(`FOREIGN`·`INSTITUTION`·`RETAIL`·`ETF`).

## 3. 테이블 (model.py) — 1차 7종

리터럴 출처는 #305. 점수 필드는 별도(중요도·감성·영향도·신뢰도를 하나로 뭉치지 않음, 스펙 §6.3).

### 3.1 `source_documents` (사실)

`id`, `document_type`(DocumentType), `source_name`, `source_url`, `external_id`(DART
접수번호 등, nullable), `title`, `raw_content`, `normalized_content`(nullable), `language`,
`published_at`, `collected_at`, `content_hash`(중복 제거 키, unique), `source_reliability`
(float 0~1), `processing_status`(ProcessingStatus), `created_at`. 인덱스: `content_hash`,
`(document_type, published_at)`.

### 3.2 `extracted_events` (사실→구조화)

`id`, `event_type`(EventType), `title`, `summary`, `importance_score`(float),
`sentiment_direction`(SentimentDirection), `sentiment_score`(float), `confidence_score`
(float), `occurred_at`(nullable), `detected_at`, `primary_symbol`(nullable), `sector_code`
(nullable), `event_fingerprint`(기업+유형+기간+핵심 엔티티 병합 키, 인덱스), `status`
(EventStatus), `created_at`. **importance_score와 sentiment는 분리 필드.**

### 3.3 `event_evidence` (이벤트↔문서)

`id`, `event_id`(FK extracted_events), `document_id`(FK source_documents), `relevance_score`
(float), `evidence_role`(EvidenceRole), `extracted_quote`(nullable), `created_at`. 인덱스:
`(event_id, evidence_role)`.

### 3.4 `topic_clusters` (추론)

`id`, `slug`(unique), `title`, `summary`(nullable), `category`(TopicCategory, nullable),
`mention_count`(int), `momentum_score`(float), `sentiment_score`(float), `impact_score`
(float), `confidence_score`(float), `lifecycle_status`(LifecycleStatus), `first_seen_at`,
`last_activity_at`, `created_at`. **연관 강도(keyword_relations)와 감성은 별도 관리.**

### 3.5 `topic_keywords`

`id`, `topic_id`(FK topic_clusters), `keyword`, `weight`(float), `sentiment_score`(float),
`category`(TopicCategory, nullable), `mention_count`(int). 인덱스: `(topic_id)`.

### 3.6 `keyword_relations`

`id`, `topic_id`(FK topic_clusters), `source_keyword`, `target_keyword`, `strength`(연관
강도 float), `cooccurrence_count`(int). **strength(연관 강도)와 sentiment는 다른 필드.**

### 3.7 `topic_insights` (추론, **버전 누적 — 덮어쓰기 금지**)

`id`, `topic_id`(FK topic_clusters), `version`(int, topic별 1부터 증가), `executive_summary`,
`why_it_matters`, `key_evidence`(구조화 JSON: event_id 참조 목록), `risk_points`(JSON),
`counter_arguments`(JSON, **필수**), `impact_score`(float), `confidence_score`(float),
`model_name`, `prompt_version`, `created_at`. unique: `(topic_id, version)`.
`fund_flow_scenarios`는 3차(#371) — 이번 범위 제외.

마이그레이션: 단일 alembic revision(`create_news_insights_models`), `versions/` 최신 head 위에 스택.

## 4. API 계약 — 1차

prefix `/api/v1/news-insights`. 응답은 `ApiResponse` 엔벨로프. 각 패널은 **개별 엔드포인트**로
분리해 부분 실패를 허용한다(스펙 §6.5). 1차는 seed mock 위에서 계약을 고정한다.

### 4.1 `GET /overview` — 개요 BFF (#301)

- query: `market`, `window`(예 `24h`), `portfolio_id`(optional).
- 응답: `as_of`, `summary`{ `high_importance_events`, `sentiment_shifts`,
  `active_topic_clusters`, `fund_flow_signals` } — 각 `{ count, change }`(전일 대비),
  `briefing`{ `summary`, `highlights`[{ `text`, `topic_id`, `evidence_count`,
  `evidence_event_ids` }], `generated_at` }.
- 화면 최초 진입 상단 데이터만. 큰 목록·그래프는 개별 엔드포인트로(과적재 금지).

### 4.2 `GET /events` — 이벤트 중심 피드 (#301)

- **문서 나열이 아니라 이벤트 중심**(같은 사건 기사 N건 = 이벤트 1건 + `evidence_count`).
- query: `types`, `symbols`, `importance`, `sentiment`, `market`, `from`, `to`, `cursor`,
  `limit`. **cursor pagination 필수.**
- item: `id`, `event_type`, `document_type`, `symbol`, `title`, `summary`,
  `importance`{ `level`, `score` }, `sentiment`{ `direction`, `score` }(**분리**),
  `source`{ `name`, `reliability` }, `published_at`, `evidence_count`, `topic_ids`.

### 4.3 AI 브리핑 근거 연결 규칙 (#302)

- 브리핑은 별도 엔드포인트가 아니라 §4.1 `/overview` 응답에 포함.
- 브리핑은 **사실을 창작하지 않고 수집 근거를 압축** — 각 highlight에 `evidence_event_ids` 연결.
- 검증 규칙: 출력 evidence ID ⊆ 존재하는 이벤트 ID (`briefing.py`에서 subset 검증, 위반 시 제외).
- LLM은 숫자(count·score)를 생성하지 않음 — 집계는 DB. 1차는 mock 고정 브리핑으로 검증 구조를 고정.

### 4.4 `GET /topics/map` — 토픽 맵 (#303)

- query: `window`(예 `7d`), `market`, `limit`.
- 응답: **백엔드가 관계 계산을 완료한** `nodes`·`edges`(FE는 렌더만).
  - node: `id`, `label`, `type`(`TOPIC`/`KEYWORD`), `mention_count`, `momentum_score`,
    `sentiment_score`, `category`.
  - edge: `source`, `target`, `strength`, `cooccurrence_count`.

### 4.5 `GET /topics/{topic_id}` — 토픽 상세 (#304)

- 응답: `title`, `tags`, `lifecycle`(LifecycleStatus), `scores`{ `impact`, `sentiment`,
  `confidence`, `momentum` }, `affected_symbols`[{ `symbol`, `exposure_score`,
  `impact_direction`, `relationship` }], `insight`{ `summary`, `why_it_matters`,
  `key_evidence`, `risk_points`, `counter_arguments`(**필수**) }, `version`, `updated_at`.
- `topic_insights` 최신 버전을 반환하되 버전은 누적 보존.

### 4.6 `GET /topics/{topic_id}/trend` — 추이 (#304)

- query: `window`, `interval`.
- 응답: `points`[{ `timestamp`, `mention_count`, `sentiment_score`, `impact_score` }],
  `markers`[{ `timestamp`, `label`, `event_id` }], `source_distribution`[{ `source_type`,
  `count`, `share` }]. 언급량·감성은 DB 집계(LLM 생성 금지).

### 4.7 `GET /topics/{topic_id}/evidence` — 근거 (#304)

- query: `types`, `direction`, `cursor`, `limit`.
- item: `event_id`, `document_id`, `evidence_role`, `document_type`, `symbol`, `title`,
  `summary`, `direction`, `relevance_score`, `source`, `published_at`.
- 2차·3차 제외: `/graph`·`/symbols`·`/scenarios`·`/explanation`.

## 5. 착수 순서 (1차)

1. #305 데이터 모델 골격(테이블·enum·마이그레이션·seed 헬퍼) — 선행.
2. #301 `/overview`·`/events` — seed 위 계약.
3. #302 브리핑 근거 연결 규칙(`briefing.py` subset 검증).
4. #303 `/topics/map`.
5. #304 `/topics/{id}`·`/trend`·`/evidence`.

#301~#304는 같은 도메인(라우터·schema·service 공유)을 수정하므로 **병렬 금지**, #305 머지 후
순차 진행한다(병렬 브랜치 계약 충돌 회피).

## 6. ADR·실패 기록 판단

- ADR: 신규 도메인·테이블 추가이나 기존 아키텍처 패턴(도메인 레이어·와이어 컨벤션)을 따르므로
  **불요**. 3층 분리 원칙은 에픽 #307에 이미 기록됨.
- 실패 기록: 해당 없음.
