# Codex Handoff Task

## Source Issue

에픽 JongEunLee310/project_stock#307 2차 인프라(#368·#369·#370 공통 선행).
설계문서: `docs/designs/307-news-intelligence-phase2.md` §1·§2.

## Task Summary

뉴스·공시 인텔리전스 2차의 데이터 골격을 추가한다: enum 5종과 테이블 4종(+ 2개 보조 조인/스테이지
테이블), alembic 마이그레이션, mock seed 헬퍼. 엔드포인트(#368·#369·#370)는 이 위에서 별도
태스크로 구현한다. 이 태스크는 **모델 계층까지**만 다룬다.

## Goal

- `news_insights` 도메인에 2차 enum·테이블이 추가되고 마이그레이션으로 생성된다.
- 계약 시연용 seed 헬퍼가 2차 테이블에 최소 샘플을 삽입한다.
- 1차 모델·계약을 변경하지 않는다.

## Background

- 1차 모델·enum은 dev에 존재한다(`app/domains/news_insights/model.py`·`types.py`·`seed.py`).
  이 브랜치는 #306 위에 스택돼 있어 1차 코드가 존재한다.
- 와이어 컨벤션: snake_case, `UtcDatetime`, 점수 float(0~1), 금액은 Decimal(문자열 직렬화).
  1차 model.py의 `_score_constraint`·컬럼 패턴을 그대로 따른다.
- `SymbolRelationship`·`InvestorType`은 #305에서 이미 정의됨 — 재사용한다.

## Implementation Scope

- `app/domains/news_insights/types.py` — 설계 §1 enum 추가: `MarketEventKind`·`ValuationBurden`·
  `AgentStage`·`AgentRunStatus`·`FlowDirection`.
- `app/domains/news_insights/model.py` — 설계 §2 테이블 추가:
  - `investor_flows`(§2.1)
  - `topic_symbol_sensitivity`(§2.2, unique `(topic_id, symbol)`)
  - `market_events`(§2.3)
  - `agent_runs`(§2.4) + `agent_run_stages`(스테이지별 상태)
  - 필요 시 `market_event_topics`(캘린더-토픽 조인) — 설계 §2.3에서 조인 대신 파생도 허용하므로,
    seed·조회를 단순화할 수 있으면 조인 테이블 없이 진행하고 그 선택을 PR에 명시.
- `app/domains/news_insights/seed.py` — 2차 테이블 mock seed 헬퍼(기존 seed와 연결되게 토픽·종목
  참조 유지). 라우트/서비스는 범위 밖.
- alembic revision 1개(`create_news_insights_phase2_models`) — 현재 head 위 스택. 모델 등록은
  기존 `app/db/models.py` import 패턴 확인(1차 등록이 이미 있으면 추가 불요).

## Out of Scope

- API 라우터·schema·service(#368·#369·#370 후속 태스크).
- 3차 테이블(fund_flow_scenarios 등). 실수집·실추출·LLM 연동.
- 1차 테이블·계약 및 #306 이벤트 상세 변경.

## Protected Files

없음.

## Requirements

- enum 값·테이블 필드는 설계 §1·§2와 정확히 일치(리터럴 임의 변경 금지).
- `investor_flows.net_value`는 금액 — Decimal 컬럼(문자열 직렬화 전제).
- `topic_symbol_sensitivity`는 exposure_score와 impact_direction을 분리, unique `(topic_id, symbol)`.
  `portfolio_weight`·`current_signal`은 저장하지 않는다(조회 시 조인 — 이 태스크 범위 밖).
- `agent_runs`/`agent_run_stages`는 검증 가능한 집계·단계만 저장(비공개 추론 과정 저장 금지).
- 마이그레이션 up/down 모두 동작한다.

## Test Requirements

- 2차 모델 생성·관계(FK)·제약(unique/index) 검증 단위 테스트.
- seed 헬퍼가 2차 테이블에 오류 없이 삽입하는지 검증.
- 마이그레이션 up/down 테스트(1차 `tests/test_news_insights_models.py` 패턴 참고).
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`
- `uv run alembic upgrade head` (환경상 실패하면 SQLite 임시 DB로 up/down 확인하고 보고)

## Documentation Impact

- 설계문서 §1·§2 계약과 구현 일치. 이탈 시 문서 먼저 갱신.

## ADR Need

불요. 1차와 동일 도메인 레이어·와이어 컨벤션을 따르는 신규 테이블 추가(설계 §5).

## Failure Record Need

불요.

## Risk Level

Low~Medium — 신규 테이블·마이그레이션. 마이그레이션 스택 순서·Decimal 컬럼 주의.

## Expected Output

- types·model·seed·마이그레이션·테스트 커밋. PR 본문에 설계문서 링크와 테이블·enum 요약.
- 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
