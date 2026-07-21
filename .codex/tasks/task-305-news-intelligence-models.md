# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#305 — BE: 뉴스 인텔리전스 데이터 모델 골격 (에픽 #307 1차 선행).
설계문서: `docs/designs/307-news-intelligence.md`.

## Task Summary

`Document → Event → Topic → Insight → Evidence` 3층 데이터 흐름을 고정하는 신규 도메인
`app/domains/news_insights/`의 ORM 모델·enum·alembic 마이그레이션·mock seed 헬퍼를 추가한다.
API 계약(#301~#304)의 기반이며, 이 태스크는 **모델 계층까지**만 다룬다.

## Goal

- `app/domains/news_insights/` 도메인이 생성되고 7개 ORM 모델과 enum이 정의된다.
- alembic 마이그레이션으로 7개 테이블이 생성된다.
- 계약 시연용 mock seed 헬퍼(`seed.py`)가 존재한다.
- 기존 스키마·계약을 변경하지 않는다.

## Background

- 설계문서 `docs/designs/307-news-intelligence.md` §1~§3에 도메인 배치·enum·테이블이 스켈레톤으로
  확정돼 있다. **이 문서를 계약의 정본으로 삼는다.**
- 와이어 컨벤션: snake_case, `app/core/schema.py`의 `UtcDatetime`, 점수 float(0~1). 기존 도메인
  (`app/domains/decision_logs/`)의 model/types 구성 패턴을 그대로 따른다.
- 사실(documents·events·evidence)과 AI 추론(topics·keywords·relations·insights)을 별도 테이블로 둔다.
- `topic_insights`는 버전 누적(덮어쓰기 금지) — unique `(topic_id, version)`.

## Implementation Scope

- `app/domains/news_insights/__init__.py`
- `app/domains/news_insights/types.py` — 설계문서 §2 enum 전체
- `app/domains/news_insights/model.py` — 설계문서 §3 테이블 7종(source_documents,
  extracted_events, event_evidence, topic_clusters, topic_keywords, keyword_relations,
  topic_insights)
- `app/domains/news_insights/seed.py` — mock seed 헬퍼(토픽 1~2개·이벤트·문서·근거·인사이트 최소
  샘플 삽입 함수). 라우트/서비스는 이 태스크 범위 밖.
- alembic revision 1개(`create_news_insights_models`) — 현재 head 위에 스택. 모델 등록(메타데이터
  import 경로)이 필요하면 기존 패턴대로 반영.

## Out of Scope

- API 라우터·schema·service·briefing(#301~#304 후속 태스크)
- `fund_flow_scenarios` 및 2차·3차 테이블(symbols·investor_flows 등)
- 실수집·실추출 파이프라인, LLM 연동
- 기존 `news`·`raw_news`·`ingestion` 도메인 및 `/assets/{id}/news-disclosure` 계약 변경

## Protected Files

없음. 기존 계약 파일은 수정하지 않는다.

## Requirements

- enum 값·테이블 필드는 설계문서 §2·§3과 정확히 일치한다(리터럴 임의 변경 금지).
- importance_score와 sentiment(direction·score)는 분리 컬럼으로 둔다.
- `source_documents.content_hash`는 unique, `extracted_events.event_fingerprint`는 인덱스.
- `topic_insights`는 unique `(topic_id, version)`.
- 마이그레이션 up/down 모두 동작한다.

## Test Requirements

- 모델 생성·관계(FK) 및 제약(unique/index) 검증 단위 테스트 최소 1개 파일.
- seed 헬퍼가 오류 없이 최소 샘플을 삽입하는지 검증.
- 기존 테스트를 약화하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy app`
- `uv run pytest`
- `uv run alembic upgrade head` (신규 마이그레이션 적용 확인)

## Documentation Impact

- `docs/designs/307-news-intelligence.md`는 이미 존재. 구현 중 계약이 바뀌면 문서를 먼저 갱신하고
  사유를 PR에 남긴다(임의 이탈 금지).

## ADR Need

불요. 기존 도메인 레이어·와이어 컨벤션을 따르는 신규 테이블 추가(설계문서 §6).

## Failure Record Need

불요.

## Risk Level

Low — 신규 파일 위주, 기존 계약 무변경. 마이그레이션 스택 순서만 주의.

## Expected Output

- 신규 도메인 파일·마이그레이션·테스트 커밋. PR 본문은 설계문서 링크와 테이블·enum 요약 포함.
- 검증 명령 4종 결과를 PR/응답에 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치를 유지한다(자체 브랜치 생성 금지).
