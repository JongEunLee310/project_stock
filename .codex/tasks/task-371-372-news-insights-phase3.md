# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#371 · #372 — BE: 예상 자금 흐름 전망·시나리오 계약(#371),
인사이트 설명가능성·반대 관점 계약(#372) (에픽 #307 3차).
설계문서: `docs/designs/307-news-intelligence-phase3.md`.

## Task Summary

3차 계약 3종을 구현한다: `GET /api/v1/news-insights/fund-flow-outlook`(섹터 자금 흐름),
`GET /topics/{topic_id}/scenarios`(낙관/기준/보수 3 시나리오), `GET /topics/{topic_id}/explanation`
(기여 요인·반대 관점). 신규 테이블 3종·enum 3종·마이그레이션·seed를 추가하고 그 위에 계약을 고정한다.
FE #267·#268이 이 계약을 소비한다.

## Goal

- `GET /fund-flow-outlook`이 섹터별 방향·수준·범위·기간·신뢰도·가정·위험을 반환한다(확정 예측 금지).
- `GET /topics/{id}/scenarios`가 항상 3개 시나리오(낙관/기준/보수)를 가중치·가정·수혜/위험 섹터·
  관련 종목·무효화 조건과 함께 반환한다.
- `GET /topics/{id}/explanation`이 기여 요인 비율·메타·반대 관점(counter_arguments·무효화 조건·
  선반영 여부·CONTRADICTING evidence)을 반환한다.
- 1·2차 계약을 변경하지 않는다.

## Background

- 1·2차 도메인이 이미 있다: `app/domains/news_insights/{model,types,schema,repository,service,
  seed}.py`, 라우트 `app/api/v1/endpoints/news_insights.py`(router는 `app/api/v1/router.py`에
  `/news-insights`로 등록됨). 3차는 같은 도메인에 추가한다.
- 와이어 컨벤션(1·2차 동일): snake_case, `UtcDatetime`, 점수·비율 float(0~1), `ApiResponse`/
  `success`, 인증 `get_current_user`. 자금 금액·범위는 **확정값을 만들지 말고 라벨 문자열**로
  표기(예 "+1.8조원").
- **정량 숫자(자금·기여 비율)는 정량 모델·규칙 기반 집계에서 산출하고 LLM은 해석·서술만.** seed는
  1·2차와 동일하게 소규모 연결 데이터로 계약을 시연·테스트할 수 있게 넣는다(`seed.py`의
  `seed_mock_news_insights` 패턴 확장 — 기존 topic·event·evidence에 연결).
- 반대 관점은 신규 테이블 없이 1차 `topic_insights.counter_arguments`와 `event_evidence`의
  `evidence_role=CONTRADICTING`를 재사용·구조화한다.
- 마이그레이션: 단일 alembic revision `create_news_insights_phase3_models`, 현재 head
  `c3d4e5f6006c`(phase2) 위에 스택. 리비전 id는 `c3d4e5f6006d` 규칙을 따른다. 파일 위치
  `alembic/versions/`.

## Implementation Scope

- `app/domains/news_insights/types.py` — enum 3종 추가: `ScenarioKind`(OPTIMISTIC·BASE·
  CONSERVATIVE), `FundFlowDirection`(INFLOW·OUTFLOW·NEUTRAL), `FlowLikelihood`(LOW·MEDIUM·HIGH).
- `app/domains/news_insights/model.py` — 테이블 3종: `fund_flow_outlooks`, `fund_flow_scenarios`,
  `topic_explanations` + `explanation_factors`. 리스트형 필드는 JSON array 컬럼(설계 §2).
- `alembic/versions/c3d4e5f6006d_create_news_insights_phase3_models.py` — 신규 테이블 생성,
  down_revision `c3d4e5f6006c`.
- `app/domains/news_insights/seed.py` — 3차 seed(기존 topic에 연결된 outlook·scenarios·
  explanation+factors).
- `app/domains/news_insights/schema.py` — 3종 응답 projection(설계 §3.1·§3.2·§3.3).
- `app/domains/news_insights/repository.py` — 신규 테이블 조회 + CONTRADICTING evidence·
  counter_arguments 조회.
- `app/domains/news_insights/service.py` — outlook 목록·시나리오 3종 조립·explanation(factors·
  meta·counter_view) 조립.
- `app/api/v1/endpoints/news_insights.py` — 라우트 3개 추가(`/fund-flow-outlook`,
  `/topics/{topic_id}/scenarios`, `/topics/{topic_id}/explanation`).

## Out of Scope

- FE(#267·#268). 실수집·실추출 파이프라인 연동(seed 계약 고정). 1·2차 로직·계약 변경.
- 통계적 확률 산출 로직(가중치는 seed 라벨 수준). 새 도메인·아키텍처 변경.

## Protected Files

없음.

## Requirements

- `GET /fund-flow-outlook`: query `market`(optional). 응답 `as_of`·`analysis_version`·`items`
  [{`sector`·`direction`(FundFlowDirection)·`likelihood`(FlowLikelihood)·`estimated_range`·
  `horizon`·`confidence`·`key_assumptions`[]·`risk_factors`[]}]. **확정 예측 표현 금지**(설계 §3.1).
- `GET /topics/{id}/scenarios`: 항상 3 시나리오. 응답 `topic_id`·`analysis_version`·`as_of`·
  `scenarios`[3]{`scenario_kind`·`weight`·`expected_flow_direction`·`key_assumptions`[]·
  `benefiting_sectors`[]·`risk_sectors`[]·`related_symbols`[]·`invalidation_conditions`[]}.
  존재하지 않는 topic_id는 404. (설계 §3.2)
- `GET /topics/{id}/explanation`: `factors`[{`label`·`contribution_ratio`}](합 ≈ 1.0)·
  `meta`{`analysis_version`·`data_coverage`·`last_updated`·`missing_data`[]·
  `counter_argument_count`·`confidence`·`limitations`[]}·`counter_view`{`counter_arguments`[]·
  `invalidation_conditions`[]·`already_priced_in`{`likely`·`note`}·`contradicting_evidence`
  [{`event_id`·`document_id`·`title`·`source`·`published_at`}]}. **반대 관점 필수.** 존재하지
  않는 topic_id는 404. (설계 §3.3)
- enum·필드·테이블은 설계문서 계약에 일치. 이탈 시 설계문서 먼저 갱신.
- 마이그레이션은 단일 head 유지(`uv run alembic heads`가 1개).

## Test Requirements

- 세 라우트 통합 테스트(httpx): outlook 필수 필드·확정예측 아닌 표기, scenarios 3종·404,
  explanation factors 합·counter_view(CONTRADICTING evidence 연결·counter_arguments) ·404.
- seed·모델 정합 테스트(기존 phase2 테스트 패턴 참고).
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 `docs/designs/307-news-intelligence-phase3.md` 계약과 구현 일치. 이탈 시 문서 먼저 갱신.

## ADR Need

불요. 1·2차와 동일 아키텍처·와이어 컨벤션을 따르는 신규 테이블·read 엔드포인트 추가이며, 사실/추론
분리는 ADR-009의 연장이다.

## Failure Record Need

불요.

## Risk Level

Medium — 신규 테이블 3종·마이그레이션·seed·엔드포인트 3개로 표면적이 넓다. 마이그레이션 단일 head,
JSON 리스트 컬럼 mypy 타입, explanation의 CONTRADICTING evidence 조인 정확성이 핵심 리스크.

## Expected Output

- types·model·마이그레이션·seed·schema·repository·service·router·테스트 커밋(한국어 메시지).
  PR은 생성하지 말고 push도 하지 마라(오케스트레이터가 처리).
- 검증 3종 결과 보고(특히 `uv run alembic heads`가 단일 head인지, `mypy .` 파일 수).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(feat/371-372-news-insights-phase3)를 유지한다(자체 브랜치 생성·push·PR 금지).
