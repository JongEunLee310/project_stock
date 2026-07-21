# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#301 (개요·이벤트 피드 계약) + #302 (AI 브리핑 근거 연결).
에픽 #307 1차. 설계문서: `docs/designs/307-news-intelligence.md` §4.1·§4.2·§4.3.

## Task Summary

`news_insights` 도메인에 개요 BFF(`GET /overview`, 브리핑 포함)와 이벤트 중심 피드
(`GET /events`, cursor pagination)를 구현한다. 브리핑은 별도 엔드포인트가 아니라 `/overview`
응답에 포함하며, 각 highlight 문장에 근거 event ID를 연결하고 subset 검증한다. 1차는 #305의
seed mock 위에서 계약을 고정한다.

## Goal

- `GET /api/v1/news-insights/overview` — 상단 요약 4종 + 브리핑을 반환한다.
- `GET /api/v1/news-insights/events` — 이벤트 중심 피드를 cursor pagination으로 반환한다.
- 브리핑 highlight의 `evidence_event_ids`가 존재하는 이벤트 ID의 부분집합임을 검증한다.
- 기존 계약(`/assets/{id}/news-disclosure` 등)을 변경하지 않는다.

## Background

- 모델·enum·seed는 #305에서 이미 추가됨(`app/domains/news_insights/model.py`·`types.py`·
  `seed.py`). 이 브랜치는 #305 위에 스택돼 있어 모델이 존재한다.
- 와이어 컨벤션: snake_case, `app/core/schema.py`의 `UtcDatetime`, 점수 float(0~1), 공통
  엔벨로프 `app/core/response.py`의 `ApiResponse`/`success`/`paginated`. cursor pagination은
  `app/core/pagination.py` 패턴을 따른다. 기존 도메인(`app/domains/decision_logs/`,
  라우터 `app/api/v1/endpoints/decision_logs.py`)의 schema/service/router 구성을 따른다.
- 인증: `app/api/v1/deps.py`의 `get_current_user` (기존 엔드포인트와 동일 정책).

## Implementation Scope

- `app/domains/news_insights/schema.py` — overview·events 요청/응답 projection.
- `app/domains/news_insights/repository.py` — events 조회(cursor)·요약 집계·토픽 조회 접근.
- `app/domains/news_insights/service.py` — overview BFF 조립, events 목록 유스케이스.
- `app/domains/news_insights/briefing.py` — 브리핑 조립 + `evidence_event_ids` subset 검증
  (존재하지 않는 ID 참조는 제외). 1차는 seed 기반 고정 브리핑으로 계약·검증 구조를 고정.
- `app/api/v1/endpoints/news_insights.py` — 라우터(신규), prefix `/api/v1/news-insights`.
- 라우터 등록(`app/api/v1/router.py` 또는 기존 등록 지점 패턴대로).

## Out of Scope

- `/topics/map`(#303), `/topics/{id}`·`/trend`·`/evidence`(#304), 이벤트 상세(#306) 및 2·3차.
- 실수집·실추출·실LLM 브리핑 생성(1차는 seed mock 고정). 새 마이그레이션 불요(#305 테이블 재사용).
- 기존 `news`·`raw_news`·`ingestion` 도메인 및 그 계약 변경.

## Protected Files

없음.

## Requirements

- `GET /overview`: query `market`·`window`·`portfolio_id`(optional). 응답 `as_of`,
  `summary`{high_importance_events·sentiment_shifts·active_topic_clusters·fund_flow_signals}
  (각 `{count, change}`), `briefing`{summary·highlights[{text·topic_id·evidence_count·
  evidence_event_ids}]·generated_at}. (설계 §4.1)
- `GET /events`: **이벤트 중심**(문서 나열 아님, 같은 사건 = 이벤트 1건 + evidence_count).
  query `types`·`symbols`·`importance`·`sentiment`·`market`·`from`·`to`·`cursor`·`limit`.
  **cursor pagination 필수.** item은 설계 §4.2 필드(importance와 sentiment 분리). (설계 §4.2)
- 브리핑 검증: 출력 evidence ID ⊆ 존재 이벤트 ID. LLM은 숫자(count·score) 생성 금지 —
  집계는 repository/service. (설계 §4.3)
- enum·필드는 #305 모델과 설계문서 계약에 일치. 계약 이탈 시 설계문서를 먼저 갱신하고 사유 기록.

## Test Requirements

- overview·events 라우트 통합 테스트(httpx) — 응답 스키마·cursor 동작·요약 4종.
- 브리핑 subset 검증 단위 테스트(존재하지 않는 evidence ID가 제외되는지).
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 `docs/designs/307-news-intelligence.md` §4 계약과 구현이 일치해야 한다. 이탈 시 문서
  먼저 갱신.

## ADR Need

불요. 기존 도메인·와이어 컨벤션을 따르는 read 엔드포인트 추가.

## Failure Record Need

불요.

## Risk Level

Low~Medium — 신규 read 엔드포인트. cursor pagination·브리핑 subset 검증 정확성에 주의.

## Expected Output

- schema·repository·service·briefing·router·테스트 커밋. PR 본문에 설계문서 링크와 계약 요약.
- 검증 3종 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
