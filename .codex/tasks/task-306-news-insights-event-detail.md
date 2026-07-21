# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#306 — BE: 이벤트 상세 계약 (에픽 #307 2차).
설계문서: `docs/designs/307-news-intelligence-phase2.md` §3.1.

## Task Summary

`news_insights` 도메인에 `GET /api/v1/news-insights/events/{event_id}`를 구현한다. 개별 이벤트의
중요도·감성·영향 종목·근거 문서·관련 토픽을 반환한다. 신규 테이블은 없고 1차 모델을 재사용한다.

## Goal

- `GET /events/{event_id}`가 이벤트 상세를 반환한다.
- 존재하지 않는 event_id는 404.
- 기존 계약(1차 엔드포인트)을 변경하지 않는다.

## Background

- 1차 모델·라우터·service·repository·schema가 dev에 이미 있다: `app/domains/news_insights/`의
  `model.py`(ExtractedEvent·EventEvidence·SourceDocument·TopicInsight)·`service.py`·
  `repository.py`·`schema.py`, 라우터 `app/api/v1/endpoints/news_insights.py`.
- 404 에러 코드 `NEWS_INSIGHT_TOPIC_NOT_FOUND`가 `app/core/error_codes.py`에 이미 있다(토픽용).
  이벤트용 not-found가 필요하면 `NEWS_INSIGHT_EVENT_NOT_FOUND`를 동일 패턴으로 추가한다.
- 와이어 컨벤션: snake_case, `ApiResponse`/`success`, 점수 float, 인증 `get_current_user`.
- 토픽↔이벤트 연결은 1차와 동일하게 `TopicInsight.key_evidence`의 event_id를 정본으로 사용한다.

## Implementation Scope

- `app/domains/news_insights/schema.py` — 이벤트 상세 projection.
- `app/domains/news_insights/repository.py` — 이벤트·근거 문서·관련 토픽 조회.
- `app/domains/news_insights/service.py` — 이벤트 상세 유스케이스(404 처리).
- `app/api/v1/endpoints/news_insights.py` — `GET /events/{event_id}` 라우트 추가.
- 필요 시 `app/core/error_codes.py`에 `NEWS_INSIGHT_EVENT_NOT_FOUND` 1건 추가.

## Out of Scope

- 투자자 동향(#368)·종목 민감도·키워드 관계망(#369)·캘린더·처리 현황(#370) 및 신규 테이블.
- 1차 엔드포인트 로직 변경. 새 마이그레이션 불요(신규 테이블 없음).

## Protected Files

없음.

## Requirements

- `GET /events/{event_id}` 응답: `event_type`, `title`, `summary`, `importance`{score·level·
  explanation}, `sentiment`{direction·score}, `affected_symbols`[{symbol·direction·
  exposure_score·reason}], `evidence`[{document_id·document_type·source·title·published_at·
  evidence_role}], `related_topics`[{topic_id·title}]. (설계 §3.1)
- 존재하지 않는 event_id는 404(표준 에러 코드).
- enum·필드는 1차 모델과 설계문서 계약에 일치. 이탈 시 설계문서 먼저 갱신.

## Test Requirements

- `/events/{event_id}` 통합 테스트(httpx) — 응답 스키마·근거·관련 토픽.
- 404 케이스 테스트.
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 §3.1 계약과 구현 일치. 이탈 시 문서 먼저 갱신.

## ADR Need

불요. 기존 도메인·와이어 컨벤션을 따르는 read 엔드포인트 추가.

## Failure Record Need

불요.

## Risk Level

Low — read 엔드포인트 1개, 신규 테이블 없음, 기존 로직 무변경.

## Expected Output

- schema·repository·service·router·테스트 커밋. PR 본문에 설계문서 링크와 계약 요약.
- 검증 3종 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
