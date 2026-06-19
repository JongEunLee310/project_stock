# 015: 투자 가설 충돌 판단

## 목적

뉴스 요약 결과와 기존 투자 가설을 LLM에 함께 입력하여
`SUPPORTS / NEUTRAL / CONFLICTS` 판단과 근거를 반환한다.

## AI 응답 스키마 (Pydantic)

```
class ThesisConflictResult(BaseModel):
    status: Literal["SUPPORTS", "NEUTRAL", "CONFLICTS"]
    reason: str                   # 판단 근거 (1~3문장)
    invalidation_triggered: bool  # 가설 무효화 조건 해당 여부
```

## DB 변경

새 테이블 `thesis_conflict_analyses`:

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | Integer PK | |
| news_item_id | FK → news_items | |
| thesis_id | FK → investment_theses | |
| status | String(20) | SUPPORTS / NEUTRAL / CONFLICTS |
| reason | Text | 판단 근거 |
| invalidation_triggered | Boolean | 무효화 조건 해당 여부 |
| created_at | DateTime(tz) | |

## 프롬프트

```
app/adapters/llm/prompts/thesis_conflict.py
  build_thesis_conflict_messages(
      thesis_summary: str,
      invalidation_conditions: str,
      news_summary: str,
      news_positive_factors: list[str],
      news_negative_factors: list[str],
  ) -> list[LLMMessage]
```

## 서비스

```
class ThesisAnalysisService:
    def __init__(self, db: Session, llm_client: LLMClient)
    def analyze_conflict(self, news_item_id: int, thesis_id: int) -> ThesisConflictResult
```

- `news_items`에서 요약 결과 조회 (없으면 예외)
- `investment_theses`에서 가설 내용 조회
- `LLMClient.complete_json(messages, ThesisConflictResult)` 호출
- 결과를 `thesis_conflict_analyses`에 저장
- `ThesisConflictResult` 반환

## 의존성

Issue #13 (LLM Adapter), #14 (뉴스 AI 요약) 완료 후 진행
