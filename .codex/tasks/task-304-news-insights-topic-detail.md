# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#304 — BE: 토픽 상세·추이·근거 계약 (에픽 #307 1차).
설계문서: `docs/designs/307-news-intelligence.md` §4.5·§4.6·§4.7.

## Task Summary

`news_insights` 도메인에 토픽 상세 3종 엔드포인트를 구현한다: `GET /topics/{topic_id}`(상세),
`GET /topics/{topic_id}/trend`(추이), `GET /topics/{topic_id}/evidence`(근거, cursor). 1차는
#305 seed mock 위에서 계약을 고정한다.

## Goal

- `GET /topics/{id}`가 토픽 헤더·점수·영향 종목·최신 insight(버전 포함)를 반환한다.
- `GET /topics/{id}/trend`가 언급량·감성·영향 추이 points, 사건 markers, 출처 분포를 반환한다.
- `GET /topics/{id}/evidence`가 근거 목록을 cursor pagination으로 반환한다.
- 존재하지 않는 topic_id는 404.

## Background

- 모델·enum·seed와 news_insights 라우터·service·repository·schema는 상위 스택 브랜치(#305·
  #301·#303)에서 이미 존재한다. TopicCluster·TopicInsight·TopicKeyword·ExtractedEvent·
  EventEvidence·SourceDocument 모델(`app/domains/news_insights/model.py`)을 사용한다.
- `TopicInsight`는 버전 누적 — 상세는 최신 버전을 반환하되 버전 번호를 응답에 담는다.
- cursor pagination은 #301에서 추가한 `app/core/pagination.py`의 `encode/decode_datetime_cursor`와
  `app/core/response.py`의 `cursor_paginated`를 재사용한다.
- 와이어 컨벤션: snake_case, `ApiResponse`/`success`/`cursor_paginated`, 점수 float, 인증
  `get_current_user`.

## Implementation Scope

- `app/domains/news_insights/schema.py` — 토픽 상세·추이·근거 projection.
- `app/domains/news_insights/repository.py` — 토픽·insight(최신 버전)·영향 종목·추이 집계·근거
  cursor 조회.
- `app/domains/news_insights/service.py` — 상세·추이·근거 유스케이스.
- `app/api/v1/endpoints/news_insights.py` — 3개 라우트 추가.

## Out of Scope

- `/topics/{id}/graph`(2차)·`/symbols`(2차)·`/scenarios`(3차)·`/explanation`(3차), 이벤트 상세(#306).
- 개요·이벤트·토픽 맵(#301·#303) 로직 변경. 새 마이그레이션 불요.

## Protected Files

없음.

## Requirements

- `GET /topics/{id}`: 응답 `title`·`tags`·`lifecycle`, `scores`{impact·sentiment·confidence·
  momentum}, `affected_symbols`[{symbol·exposure_score·impact_direction·relationship}],
  `insight`{summary·why_it_matters·key_evidence·risk_points·**counter_arguments(필수)**},
  `version`·`updated_at`. (설계 §4.5)
- `GET /topics/{id}/trend`: query `window`·`interval`. 응답 `points`[{timestamp·mention_count·
  sentiment_score·impact_score}]·`markers`[{timestamp·label·event_id}]·`source_distribution`
  [{source_type·count·share}]. 언급량·감성은 집계(LLM 생성 금지). (설계 §4.6)
- `GET /topics/{id}/evidence`: query `types`·`direction`·`cursor`·`limit`. item은 설계 §4.7
  필드(event_id·document_id·evidence_role·document_type·symbol·title·summary·direction·
  relevance_score·source·published_at). **cursor pagination.**
- 존재하지 않는 topic_id는 404.
- enum·필드는 #305 모델과 설계문서 계약에 일치. 이탈 시 설계문서 먼저 갱신.

## Test Requirements

- 3개 라우트 통합 테스트(httpx) — 상세 응답(버전·counter_arguments)·추이 구조·근거 cursor.
- 404 케이스 테스트.
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 §4.5·§4.6·§4.7 계약과 구현 일치. 이탈 시 문서 먼저 갱신.

## ADR Need

불요. 기존 도메인·와이어 컨벤션을 따르는 read 엔드포인트 추가.

## Failure Record Need

불요.

## Risk Level

Low~Medium — read 엔드포인트 3개. 추이 집계·근거 cursor·최신 버전 선택 정확성에 주의.

## Expected Output

- schema·repository·service·router·테스트 커밋. PR 본문에 설계문서 링크와 계약 요약.
- 검증 3종 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
