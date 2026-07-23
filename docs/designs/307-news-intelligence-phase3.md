# BE 설계: 뉴스·공시 인텔리전스 3차 — 이슈 #307 (#371·#372)

상태: **계약 확정(Frozen)** — 2026-07-22. 에픽 BE #307, FE 에픽
`project_stock_frontend#198`. 1차 설계문서: `docs/designs/307-news-intelligence.md`. 2차 설계
문서: `docs/designs/307-news-intelligence-phase2.md`.

이 문서는 3차 범위(예상 자금 흐름 전망·시나리오 #371, 인사이트 설명가능성·반대 관점 #372)를
스켈레톤 수준으로 확정한다. 테이블·enum·API 계약만 담고 쿼리·비즈니스 로직은 담지 않는다.
리터럴 출처는 사용자 제공 설계 지침(스펙 §3.6·§5.9·§5.10·§5.11)과 1·2차 계약이다. 출처를 댈 수
없는 값은 "가정"으로 표기한다.

## 배경

3차는 1·2차 위에 (a) 섹터별 예상 자금 흐름과 토픽별 시나리오, (b) 인사이트가 도출된 근거를
설명하는 기여 요인·반대 관점을 추가한다. **근거 데이터가 약한 상태에서 화려한 숫자만 만들지 않도록
3차로 미뤘으며**, `Document→Event→Topic→Evidence` 안정화 이후 착수한다. 원칙은 1·2차와 동일하다:
사실과 AI 추론 분리, 근거 연결, **정량 숫자(자금 금액·기여 비율)는 정량 모델·규칙 기반 집계에서
산출하고 LLM은 해석·서술만** 한다. 자금 흐름은 점 예측이 아니라 방향·수준·구간·가중치로만
표기한다. 하나의 토픽을 강화하는 근거만 모으는 편향을 막기 위해 반대 관점을 의무 포함한다.

와이어 컨벤션은 1·2차와 동일하다: snake_case, `UtcDatetime`, 점수·비율 float(0~1),
`ApiResponse`/`success`, 인증 `get_current_user`. 자금 금액은 하한·상한을 갖는 구간으로 제공하며
`Decimal`을 문자열로 직렬화한다(2차 `net_value` 선례). 단위는 통화의 기본 단위이고 억·조 같은
표시 단위 변환은 화면이 맡는다.

**금액 표현은 ADR-017로 갱신됐다.** 초기 3차 설계는 확정값을 만들지 않기 위해 금액을 라벨
문자열(예 "+1.8조원")로 표기하기로 했으나, 그 형태로는 설계가 요구하는 크기 비교를 화면에서
할 수 없었고 화면이 정성 필드 나열로 흘렀다. 금지 대상은 **점 예측**이지 **구간**이 아니라는
구분을 세우고, 하한·상한을 함께 제시하는 수치 구간으로 바꿨다. 구간은 불확실성을 감추지 않고
폭으로 드러낸다. 구간을 대표하는 단일 수치 필드는 두지 않는다.

## 1. Enum 추가 (types.py)

`ScenarioKind`: `OPTIMISTIC`, `BASE`, `CONSERVATIVE`. (출처: 스펙 §5.9 낙관/기준/보수 3
시나리오.)

`FundFlowDirection`: `INFLOW`, `OUTFLOW`, `NEUTRAL`. (출처: 스펙 §3.6 자금 유입·유출. 투자자
매매 방향 `FlowDirection`(BUY/SELL/NEUTRAL)과 구분 — 섹터 자금 이동용.)

`FlowLikelihood`: `LOW`, `MEDIUM`, `HIGH`. (출처: 스펙 §3.6 가능성 수준. 확정 확률이 아닌 표시용
수준 라벨.)

## 2. 테이블 추가 (model.py) — 3차 3종

`counter_arguments`·CONTRADICTING evidence는 신규 테이블 없이 1차 모델(`topic_insights`의
`counter_arguments`, `event_evidence`의 `evidence_role=CONTRADICTING`)을 재사용·구조화한다.
신규 테이블은 3종이다. 리스트형 필드(가정·위험·섹터·종목 목록)는 JSON array 컬럼으로 저장한다
(자식 테이블 없이 스켈레톤 단순화).

### 2.1 `fund_flow_outlooks` (#371 /fund-flow-outlook)

`id`, `sector`, `direction`(FundFlowDirection), `likelihood`(FlowLikelihood),
`estimated_flow_low`·`estimated_flow_high`(Decimal, nullable — 통화 기본 단위)·
`estimated_flow_currency`(str, nullable), `horizon`(str 라벨 — 예 "2~4주"), `confidence`(float 0~1),
`key_assumptions`(JSON list[str]), `risk_factors`(JSON list[str]), `analysis_version`(str),
`as_of`, `created_at`. 인덱스: `(analysis_version, sector)`. **점 예측 금지, 구간 허용**
(ADR-017) — 방향·수준·구간·기간·신뢰도·가정·위험·분석 버전을 필수로 함께 제공(스펙 §3.6).
금액은 하한·상한을 함께 갖거나 셋 다 비운다. 반열린 구간과 구간 대표 단일 수치는 두지 않는다.

### 2.2 `fund_flow_scenarios` (#371 /topics/{id}/scenarios)

`id`, `topic_id`(FK topic_clusters), `scenario_kind`(ScenarioKind), `weight`(float 0~1 — 현재
근거 기준 가중치), `expected_flow_direction`(FundFlowDirection), `expected_net_flow_low`·
`expected_net_flow_high`(Decimal, nullable)·`expected_net_flow_currency`(str, nullable),
`key_assumptions`(JSON list[str]),
`benefiting_sectors`(JSON list[str]), `risk_sectors`(JSON list[str]), `related_symbols`(JSON
list[str]), `invalidation_conditions`(JSON list[str]), `analysis_version`(str), `created_at`.
unique: `(topic_id, analysis_version, scenario_kind)`. **버전 누적** — analysis_version별로 3행
(낙관·기준·보수) 저장. weight 합은 100%가 될 수 있으나 통계적 확률로 과표현하지 않는다(가중치
라벨).

### 2.3 `topic_explanations` (#372 /topics/{id}/explanation)

`id`, `topic_id`(FK topic_clusters), `analysis_version`(str), `data_coverage`(float 0~1),
`confidence`(float 0~1), `missing_data`(JSON list[str]), `limitations`(JSON list[str]),
`already_priced_in`(bool), `already_priced_in_note`(str, nullable), `last_updated`,
`created_at`. unique: `(topic_id, analysis_version)`. 기여 요인은 `explanation_factors`
(id·topic_explanation_id(FK)·label·contribution_ratio(float 0~1)·display_order)로 분리 —
비율 합 ≈ 1.0. **기여 비율은 정량 모델 기여도 또는 규칙 기반 집계에서 산출**하며 LLM이 임의
작성하지 않는다(스펙 §5.10).

마이그레이션: 단일 alembic revision(`create_news_insights_phase3_models`), 2차 head 위 스택.

## 3. API 계약 — 3차 (prefix `/api/v1/news-insights`)

### 3.1 `GET /fund-flow-outlook` — 예상 자금 흐름 (#371)

- query: 없음(3차 골격은 최신 analysis_version 전체 반환. `fund_flow_outlooks`에 market 컬럼이
  없어 시장 필터는 두지 않는다 — 필요 시 컬럼과 파라미터를 함께 추가).
- 응답: `as_of`, `analysis_version`, `items`[{`sector`·`direction`·`likelihood`·
  `estimated_flow`{`low`·`high`(Decimal 문자열)·`currency`} 또는 `null`·`horizon`·`confidence`·
  `key_assumptions`[]·`risk_factors`[]}].
- **점 예측 금지, 구간 허용**(ADR-017) — 금액은 하한·상한을 함께 제시하고, 산출되지 않으면
  `estimated_flow`를 `null`로 둔다. 구간을 대표하는 단일 수치 필드는 두지 않는다. 자금 숫자는
  정량 집계, LLM은 방향·가정 서술만. `fund_flow_outlooks` 기반.

### 3.2 `GET /topics/{topic_id}/scenarios` — 자금 흐름 시나리오 (#371)

- 단일 전망이 아니라 3개 시나리오(낙관/기준/보수)를 항상 함께 반환.
- 응답: `topic_id`, `analysis_version`, `as_of`, `scenarios`[3]{`scenario_kind`·`weight`·
  `expected_flow_direction`·`expected_net_flow`{`low`·`high`·`currency`} 또는 `null`·
  `key_assumptions`[]·`benefiting_sectors`[]·`risk_sectors`[]·
  `related_symbols`[]·`invalidation_conditions`[]}.
- `weight`는 현재 근거 기준 가중치(합 100% 가능하나 통계적 확률로 과표현 금지). 존재하지 않는
  topic_id는 404. `fund_flow_scenarios` 기반.

### 3.3 `GET /topics/{topic_id}/explanation` — 왜 이런 인사이트·반대 관점 (#372)

- 응답 `factors`[{`label`·`contribution_ratio`}] — 기여 요인 비율(합 ≈ 1.0, 정량·규칙 산출).
- 응답 `meta`{`analysis_version`·`data_coverage`·`last_updated`·`missing_data`[]·
  `counter_argument_count`·`confidence`·`limitations`[]}.
- 응답 `counter_view`{`counter_arguments`[]·`invalidation_conditions`[]·
  `already_priced_in`{`likely`(bool)·`note`}·`contradicting_evidence`[{`event_id`·`document_id`·
  `title`·`source`·`published_at`}]} — **반대 관점 필수**(스펙 §5.11).
- 반대 관점은 #304 토픽 상세의 `counter_arguments`와 `event_evidence`의 CONTRADICTING evidence를
  확장·구조화한다. 기여 비율(숫자)은 정량 로직, LLM 역할은 반대 관점 문장 생성·구조화. 존재하지
  않는 topic_id는 404. `topic_explanations`·`explanation_factors` 기반.

## 4. 착수 순서 (3차)

1. 모델 추가(자금 흐름 outlook·시나리오·설명 3종) + 마이그레이션 + seed — #371·#372 공통 선행.
2. #371 자금 흐름 전망·시나리오 → #372 설명·반대 관점.

모두 같은 도메인(라우터·schema·service 공유)을 수정하므로 **병렬 금지**, 순차 진행한다. 각 PR은
**base=dev**로 열고 브랜치만 스택한다(중간 브랜치 base 금지 — 스택 머지 함정 회피).

## 5. ADR·실패 기록 판단

- ADR: 신규 테이블·enum 추가이나 1·2차와 동일 아키텍처 패턴·와이어 컨벤션을 따르고, 반대 관점·기여
  비율의 사실/추론 분리 원칙도 기존 결정(ADR-009)의 연장이므로 **불요**.
- 실패 기록: 해당 없음.
