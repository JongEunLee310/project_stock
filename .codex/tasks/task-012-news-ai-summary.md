# Codex Handoff Task

## Source Issue

Issue #14: 뉴스 AI 요약 기능 구현

## Task Summary

수집된 뉴스 원문을 LLM이 구조화된 JSON으로 요약한다. 긍정/부정 요인 분리, 영향도 분류, Pydantic 검증, `news_items` 업데이트를 구현한다.

## Goal

- 뉴스 원문을 `NewsSummaryResult` 스키마로 변환할 수 있다.
- AI 응답이 스키마에 맞지 않으면 저장하지 않는다.
- 요약, 영향도, 긍정/부정 요인을 `news_items`에서 조회할 수 있다.

## Background

- **설계 문서를 구현 전에 반드시 읽는다:** `docs/designs/014-news-ai-summary.md`
- task-011 (LLM Adapter) 완료 후 진행.
- `news_items` 테이블에 `positive_factors`, `negative_factors` 컬럼이 없다 — Alembic 마이그레이션 추가 필요.
- 기존 `summary`, `sentiment`, `impact_level` 컬럼은 이미 존재하므로 재사용한다.
- `positive_factors`, `negative_factors`는 JSON 배열 문자열로 저장한다 (`json.dumps(list[str])`).
- `NewsAnalysisService`는 `LLMClient`를 생성자 주입으로 받는다. 서비스가 직접 `OpenAIClient`를 생성하지 않는다.

## Implementation Scope

- `alembic/versions/<hash>_add_news_item_factors.py` — `positive_factors`, `negative_factors` 컬럼 추가 마이그레이션
- `app/domains/news/model.py` — 두 컬럼 필드 추가
- `app/domains/news/schema.py` — `NewsSummaryResult`, `NewsItemResponse` 업데이트
- `app/domains/news/repository.py` — `update_summary(news_item_id, data: NewsSummaryResult)` 메서드 추가
- `app/adapters/llm/prompts/news_summary.py` — `build_news_summary_messages(title, body) -> list[LLMMessage]`
- `app/domains/news/service.py` (또는 `app/domains/news/analysis.py`) — `NewsAnalysisService` 클래스
- `tests/test_news_analysis.py`

## Out of Scope

- Worker job에 통합 (Issue #19 이후)
- 분석 API 엔드포인트 (Issue #16에서 처리)
- 투자 가설 충돌 판단 (Issue #15)

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### Alembic 마이그레이션

`positive_factors TEXT NULL`, `negative_factors TEXT NULL` 컬럼을 `news_items`에 추가.

### app/domains/news/model.py 변경

```python
positive_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
negative_factors: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### NewsSummaryResult 스키마 (app/domains/news/schema.py)

```python
class NewsSummaryResult(BaseModel):
    summary: str
    positive_factors: list[str]
    negative_factors: list[str]
    impact_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
```

### 프롬프트 (app/adapters/llm/prompts/news_summary.py)

`build_news_summary_messages(title: str, body: str) -> list[LLMMessage]`

- system 메시지: 주식 뉴스 분석가 역할, JSON 응답 지시
- user 메시지: 제목과 본문 포함
- `NewsSummaryResult.model_json_schema()`를 system 메시지에 포함

### NewsAnalysisService

```python
class NewsAnalysisService:
    def __init__(self, db: Session, llm_client: LLMClient)
    def summarize(self, news_item_id: int) -> NewsSummaryResult
```

1. `news_items`에서 `news_item_id`로 원문 조회 — 없으면 `ValueError` 발생
2. `build_news_summary_messages(title, body)` 호출
3. `llm_client.complete_json(messages, NewsSummaryResult)` 호출
4. 반환 dict를 `NewsSummaryResult.model_validate(...)` — 실패 시 `ValidationError` 전파 (저장하지 않음)
5. `repository.update_summary(news_item_id, result)` 호출
6. `NewsSummaryResult` 반환

### repository.update_summary

`summary`, `sentiment`, `impact_level`, `positive_factors`(json.dumps), `negative_factors`(json.dumps) 업데이트.

## Test Requirements

`tests/test_news_analysis.py`:

- `NewsAnalysisService.summarize` — `MockLLMClient`로 정상 흐름 검증, `news_items` 업데이트 확인 (SQLite in-memory)
- `NewsAnalysisService.summarize` — LLM이 스키마 불일치 응답 반환 시 `ValidationError` 발생, DB 미업데이트 검증
- `NewsAnalysisService.summarize` — 존재하지 않는 `news_item_id` 입력 시 `ValueError` 발생 검증
- `build_news_summary_messages` — 반환 메시지에 제목·본문이 포함되는지 검증

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_news_analysis.py -v
```

## Documentation Impact

없음.

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Medium — Alembic 마이그레이션 포함. 기존 `news_items` 모델·스키마 변경.

## Expected Output

- 위 scope 파일 신규 생성 및 수정
- Alembic 마이그레이션 파일 신규 생성
- `uv run pytest tests/test_news_analysis.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 `docs/designs/014-news-ai-summary.md`를 읽는다.
- task-011 완료 여부 확인 후 진행한다.
- `NewsAnalysisService`가 `LLMClient` 구현체를 직접 import하거나 생성하지 않는다.
- 테스트는 `MockLLMClient`만 사용한다 — OpenAI API 실제 호출 금지.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
