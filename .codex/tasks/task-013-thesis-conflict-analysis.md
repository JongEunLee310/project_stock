# Codex Handoff Task

## Source Issue

Issue #15: 투자 가설 충돌 여부 판단 기능 구현

## Task Summary

뉴스 요약 결과와 투자 가설을 LLM에 입력하여 `SUPPORTS / NEUTRAL / CONFLICTS` 판단과 근거를 생성하고 `thesis_conflict_analyses` 테이블에 저장한다.

## Goal

- 뉴스가 투자 가설과 충돌하는지 판단할 수 있다.
- 판단 결과에 근거가 함께 저장된다.
- 투자 가설 무효화 조건 해당 여부가 기록된다.

## Background

- **설계 문서를 구현 전에 반드시 읽는다:** `docs/designs/015-thesis-conflict-analysis.md`
- task-011 (LLM Adapter), task-012 (뉴스 AI 요약) 완료 후 진행.
- `news_items.summary`, `positive_factors`, `negative_factors`가 없으면 분석 불가 — `ValueError` 발생.
- `investment_theses.invalidation_conditions`가 `None`이면 빈 문자열로 처리한다.
- 결과는 `thesis_conflict_analyses` 신규 테이블에 저장한다.
- 동일 `(news_item_id, thesis_id)` 조합의 중복 저장은 허용한다 (재분석 가능).

## Implementation Scope

- `alembic/versions/<hash>_create_thesis_conflict_analyses.py` — 신규 테이블 마이그레이션
- `app/domains/theses/conflict_model.py` — `ThesisConflictAnalysis` SQLAlchemy 모델
- `app/domains/theses/conflict_schema.py` — `ThesisConflictResult`, `ThesisConflictAnalysisResponse`
- `app/domains/theses/conflict_repository.py` — `ThesisConflictRepository`
- `app/adapters/llm/prompts/thesis_conflict.py` — `build_thesis_conflict_messages(...)`
- `app/domains/theses/conflict_service.py` — `ThesisAnalysisService`
- `tests/test_thesis_conflict.py`

## Out of Scope

- 알림(Signal) 생성 연동 (향후 이슈)
- Research Report와의 연결 (Issue #16에서 처리)
- API 엔드포인트 (Issue #16에서 처리)

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### Alembic 마이그레이션 — thesis_conflict_analyses

```
id               INTEGER PK
news_item_id     INTEGER FK(news_items.id) NOT NULL INDEX
thesis_id        INTEGER FK(investment_theses.id) NOT NULL INDEX
status           VARCHAR(20) NOT NULL   -- SUPPORTS / NEUTRAL / CONFLICTS
reason           TEXT NOT NULL
invalidation_triggered BOOLEAN NOT NULL DEFAULT false
created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
```

### ThesisConflictResult 스키마

```python
class ThesisConflictResult(BaseModel):
    status: Literal["SUPPORTS", "NEUTRAL", "CONFLICTS"]
    reason: str
    invalidation_triggered: bool
```

### ThesisConflictAnalysisResponse 스키마

```python
class ThesisConflictAnalysisResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    news_item_id: int
    thesis_id: int
    status: str
    reason: str
    invalidation_triggered: bool
    created_at: datetime
```

### 프롬프트 (app/adapters/llm/prompts/thesis_conflict.py)

```python
def build_thesis_conflict_messages(
    thesis_summary: str,
    invalidation_conditions: str,
    news_summary: str,
    news_positive_factors: list[str],
    news_negative_factors: list[str],
) -> list[LLMMessage]
```

- system 메시지: 투자 가설 충돌 분석가 역할, JSON 응답 지시
- `ThesisConflictResult.model_json_schema()` 포함
- user 메시지: 가설 내용, 무효화 조건, 뉴스 요약, 긍정/부정 요인 포함

### ThesisAnalysisService

```python
class ThesisAnalysisService:
    def __init__(self, db: Session, llm_client: LLMClient)
    def analyze_conflict(self, news_item_id: int, thesis_id: int) -> ThesisConflictResult
```

1. `news_items`에서 조회 — `summary`가 없으면 `ValueError("뉴스 요약 없음")`
2. `positive_factors`, `negative_factors` JSON 파싱 (`json.loads`, 없으면 빈 리스트)
3. `investment_theses`에서 조회
4. `build_thesis_conflict_messages(...)` 호출
5. `llm_client.complete_json(messages, ThesisConflictResult)` 호출
6. `ThesisConflictResult.model_validate(...)` — 실패 시 예외 전파
7. `thesis_conflict_analyses`에 결과 저장
8. `ThesisConflictResult` 반환

### ThesisConflictRepository

```python
class ThesisConflictRepository:
    def __init__(self, db: Session)
    def create(self, news_item_id: int, thesis_id: int, result: ThesisConflictResult) -> ThesisConflictAnalysis
    def get_by_news_and_thesis(self, news_item_id: int, thesis_id: int) -> list[ThesisConflictAnalysis]
```

## Test Requirements

`tests/test_thesis_conflict.py`:

- `ThesisAnalysisService.analyze_conflict` — `MockLLMClient`로 정상 흐름 검증, DB 저장 확인 (SQLite in-memory)
- `ThesisAnalysisService.analyze_conflict` — `news_items.summary`가 없을 때 `ValueError` 발생 검증
- `ThesisAnalysisService.analyze_conflict` — LLM 응답이 스키마 불일치 시 `ValidationError` 발생, DB 미저장 검증
- `build_thesis_conflict_messages` — 가설·뉴스 내용이 메시지에 포함되는지 검증

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_thesis_conflict.py -v
```

## Documentation Impact

없음.

## ADR Need

없음.

## Failure Record Need

없음.

## Risk Level

Medium — 신규 테이블 마이그레이션 포함. 기존 `theses`, `news` 도메인 DB 조회.

## Expected Output

- 위 scope 파일 신규 생성
- Alembic 마이그레이션 파일 신규 생성
- `uv run pytest tests/test_thesis_conflict.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 `docs/designs/015-thesis-conflict-analysis.md`를 읽는다.
- task-011, task-012 완료 후 진행한다.
- `ThesisAnalysisService`가 `LLMClient` 구현체를 직접 생성하지 않는다.
- 테스트는 `MockLLMClient`만 사용한다 — OpenAI API 실제 호출 금지.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
