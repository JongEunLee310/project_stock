# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#369 — BE: 종목 민감도·키워드 관계망 계약 (에픽 #307 2차).
설계문서: `docs/designs/307-news-intelligence-phase2.md` §3.3·§3.4.

## Task Summary

토픽 상세의 두 패널 계약을 구현한다: `GET /topics/{topic_id}/symbols`(종목 민감도)와
`GET /topics/{topic_id}/graph`(키워드 관계망). 민감도는 2차 골격 `topic_symbol_sensitivity`
위에서, 관계망은 1차 `keyword_relations` 위에서 계약을 고정한다.

## Goal

- `GET /topics/{id}/symbols`가 종목별 노출도·영향 방향·관계 유형·밸류 부담과 보유 비중·현재
  시그널을 반환한다.
- `GET /topics/{id}/graph`가 토픽 내부 키워드 nodes·edges를 반환하며 노드에 관련 이벤트·종목
  참조를 포함한다.
- 존재하지 않는 topic_id는 404.

## Background

- `topic_symbol_sensitivity`(2차 골격)·`keyword_relations`·`topic_keywords`(1차) 테이블과 seed가
  이미 존재한다. `app/domains/news_insights/`의 model·types·seed·service·repository 참고.
- 토픽 404는 기존 `NEWS_INSIGHT_TOPIC_NOT_FOUND`(`app/core/error_codes.py`)를 재사용한다.
- `portfolio_weight`·`current_signal`은 `topic_symbol_sensitivity`에 저장돼 있지 않다. 설계 §2.2대로
  조회 시 portfolios·signals 도메인에서 조인/파생한다. **연결이 복잡하면 1차 범위에서는 nullable로
  두고(해당 종목 미보유·시그널 없음 = null) 조인은 최소화**하되, 그 선택을 PR에 명시한다.
- 와이어 컨벤션: snake_case, `ApiResponse`/`success`, 점수 float, 인증 `get_current_user`.

## Implementation Scope

- `app/domains/news_insights/schema.py` — symbols·graph 요청/응답 projection.
- `app/domains/news_insights/repository.py` — topic_symbol_sensitivity 조회, keyword_relations·
  topic_keywords 조회, (가능 시) portfolios·signals 조인.
- `app/domains/news_insights/service.py` — 민감도·관계망 조립.
- `app/api/v1/endpoints/news_insights.py` — 두 라우트 추가.

## Out of Scope

- 캘린더·처리 현황(#370), 자금 흐름(3차). 신규 테이블·마이그레이션 불요(골격 재사용).
- 1차·#306·#368 로직 변경. 개요 토픽 맵(#303)은 별개 — 이 graph는 토픽 내부 상세 관계망.

## Protected Files

없음.

## Requirements

- `GET /topics/{id}/symbols` item: `symbol`·`exposure_score`·`impact_direction`·`relationship`
  (DIRECT/SUPPLY_CHAIN/COMPETITOR/CUSTOMER)·`valuation_burden`·`portfolio_weight`(보유 시 조인,
  아니면 null)·`current_signal`(signals 조인, 아니면 null). **노출도(exposure_score)와 영향
  방향(impact_direction) 분리.** (설계 §3.3)
- `GET /topics/{id}/graph`: 응답 `nodes`[{id·label·type·mention_count·sentiment_score·
  related_event_ids·related_symbols}]·`edges`[{source·target·strength·cooccurrence_count}].
  **연관 강도와 감성 분리.** (설계 §3.4)
- 존재하지 않는 topic_id는 404.
- enum·필드는 골격 모델과 설계문서 계약에 일치. 이탈 시 설계문서 먼저 갱신.

## Test Requirements

- 두 라우트 통합 테스트(httpx) — 민감도 필드(노출도/방향 분리)·관계망 node/edge·404.
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`  (전체 — tests·alembic 포함. `mypy app`만으로는 CI를 재현하지 못한다.)
- `uv run pytest`

## Documentation Impact

- 설계문서 §3.3·§3.4 계약과 구현 일치. 이탈 시 문서 먼저 갱신. portfolio_weight·current_signal의
  조인 여부/nullable 처리 선택을 PR에 명시.

## ADR Need

불요. 기존 도메인·와이어 컨벤션을 따르는 read 엔드포인트 추가.

## Failure Record Need

불요.

## Risk Level

Low~Medium — read 엔드포인트 2개. 노출도/방향 분리·크로스 도메인 조인(portfolios·signals) 주의.

## Expected Output

- schema·repository·service·router·테스트 커밋. PR 본문에 설계문서 링크와 계약 요약.
- 검증 3종 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
