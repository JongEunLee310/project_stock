# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#370 — BE: 이벤트 캘린더·에이전트 처리 현황 계약 (에픽 #307 2차).
설계문서: `docs/designs/307-news-intelligence-phase2.md` §3.5·§3.6.

## Task Summary

개요 화면의 두 패널 계약을 구현한다: `GET /api/v1/news-insights/calendar`(이벤트 타임라인)와
`GET /api/v1/news-insights/agent-runs`(에이전트 처리 현황). 2차 골격 `market_events`·
`market_event_topics`·`agent_runs`·`agent_run_stages` 위에서 계약을 고정한다.

## Goal

- `GET /calendar`가 예정 이벤트를 window·market·topic_id 기준으로 반환하고 관련 토픽을 연결한다.
- `GET /agent-runs`가 최근 처리 현황(집계 수치·단계 상태·지연 여부)을 반환한다.
- 기존 계약을 변경하지 않는다.

## Background

- `market_events`·`market_event_topics`·`agent_runs`·`agent_run_stages` 테이블·`MarketEventKind`·
  `AgentStage`·`AgentRunStatus` enum·seed가 이미 존재한다(2차 골격). model·types·seed 참고.
- 와이어 컨벤션: snake_case, `UtcDatetime`, `ApiResponse`/`success`, 점수 float, 인증
  `get_current_user`.
- **agent-runs는 검증 가능한 처리 단계·집계 수치만 반환한다.** 비공개 추론 과정은 노출하지 않는다.

## Implementation Scope

- `app/domains/news_insights/schema.py` — calendar·agent-runs 요청/응답 projection.
- `app/domains/news_insights/repository.py` — market_events(+topic 조인)·agent_runs(+stages) 조회.
- `app/domains/news_insights/service.py` — 캘린더 조립(related_topic_ids), 처리 현황 요약.
- `app/api/v1/endpoints/news_insights.py` — 두 라우트 추가.

## Out of Scope

- 자금 흐름(3차). 신규 테이블·마이그레이션 불요(골격 재사용).
- 1차·#306·#368·#369 로직 변경. 실수집·실추출 파이프라인 연동(1차/2차 seed 계약 고정).

## Protected Files

없음.

## Requirements

- `GET /calendar`: query `window`(예 `5d`)·`market`·`topic_id`(optional). item: `scheduled_at`·
  `event_kind`·`title`·`symbol`·`market`·`importance`·`related_topic_ids`. (설계 §3.5)
  `market_event_topics` 조인으로 related_topic_ids 조립.
- `GET /agent-runs`: 최근 run 요약 — `last_processed_at`·`processed_documents`·`extracted_events`·
  `active_topics`·`stages`[{name·status·delayed}]·`analysis_version`·`has_delay`(bool).
  **검증 가능한 집계·단계만.** (설계 §3.6)
- enum·필드는 골격 모델과 설계문서 계약에 일치. 이탈 시 설계문서 먼저 갱신.

## Test Requirements

- 두 라우트 통합 테스트(httpx) — 캘린더 item·related_topic_ids, agent-runs 집계·단계·지연.
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 §3.5·§3.6 계약과 구현 일치. 이탈 시 문서 먼저 갱신.

## ADR Need

불요. 기존 도메인·와이어 컨벤션을 따르는 read 엔드포인트 추가.

## Failure Record Need

불요.

## Risk Level

Low~Medium — read 엔드포인트 2개. 캘린더 토픽 조인·처리 현황 집계 정확성에 주의.

## Expected Output

- schema·repository·service·router·테스트 커밋. PR 본문에 설계문서 링크와 계약 요약.
- 검증 3종 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
