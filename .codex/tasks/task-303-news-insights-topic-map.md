# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#303 — BE: 토픽 맵 계약 (에픽 #307 1차).
설계문서: `docs/designs/307-news-intelligence.md` §4.4.

## Task Summary

`news_insights` 도메인에 `GET /api/v1/news-insights/topics/map`을 구현한다. 백엔드가 관계
계산을 완료한 nodes·edges를 반환하고 FE는 렌더만 한다. 1차는 #305 seed mock(topic_clusters·
topic_keywords·keyword_relations) 위에서 계약을 고정한다.

## Goal

- `GET /topics/map`이 window·market·limit로 nodes·edges를 반환한다.
- node는 토픽·키워드를 구분하고, edge는 키워드 연관 강도를 담는다.
- 연관 강도(strength)와 감성(sentiment_score)을 별도 필드로 유지한다.

## Background

- 모델·enum·seed·개요 라우터는 #305·#301(현재 스택된 상위 브랜치)에서 이미 존재한다:
  `app/domains/news_insights/`의 `model.py`(TopicCluster·TopicKeyword·KeywordRelation)·
  `service.py`·`repository.py`·`schema.py`, 라우터 `app/api/v1/endpoints/news_insights.py`.
- 와이어 컨벤션: snake_case, `ApiResponse`/`success` 엔벨로프, 점수 float. 인증은
  `get_current_user`(개요·이벤트 엔드포인트와 동일).

## Implementation Scope

- `app/domains/news_insights/schema.py` — 토픽 맵 요청/응답 projection(TopicMapNode·TopicMapEdge).
- `app/domains/news_insights/repository.py` — topic_clusters·topic_keywords·keyword_relations 조회.
- `app/domains/news_insights/service.py` — nodes·edges 조립(관계 계산 완료 형태로 반환).
- `app/api/v1/endpoints/news_insights.py` — `GET /topics/map` 라우트 추가.

## Out of Scope

- `/topics/{id}`·`/trend`·`/evidence`(#304), 이벤트 상세(#306), `/graph`(2차) 및 2·3차.
- 실클러스터링(임베딩+클러스터링+LLM 라벨링) — 1차는 seed 위 계약 고정. 새 마이그레이션 불요.
- 개요·이벤트 엔드포인트(#301) 로직 변경.

## Protected Files

없음.

## Requirements

- `GET /topics/map`: query `window`(예 `7d`)·`market`·`limit`.
- 응답: `nodes`[{ `id`·`label`·`type`(`TOPIC`/`KEYWORD`)·`mention_count`·`momentum_score`·
  `sentiment_score`·`category` }], `edges`[{ `source`·`target`·`strength`·`cooccurrence_count` }].
  (설계 §4.4)
- **연관 강도(strength)와 감성(sentiment_score)은 별도 필드** — 하나의 숫자로 뭉치지 않는다.
- enum·필드는 #305 모델과 설계문서 계약에 일치. 이탈 시 설계문서를 먼저 갱신하고 사유 기록.

## Test Requirements

- `/topics/map` 통합 테스트(httpx) — node/edge 스키마·type 구분·window/limit 반영.
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 §4.4 계약과 구현 일치. 이탈 시 문서 먼저 갱신.

## ADR Need

불요. 기존 도메인·와이어 컨벤션을 따르는 read 엔드포인트 추가.

## Failure Record Need

불요.

## Risk Level

Low — 신규 read 엔드포인트 1개, 기존 로직 무변경.

## Expected Output

- schema·repository·service·router·테스트 커밋. PR 본문에 설계문서 링크와 계약 요약.
- 검증 3종 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
