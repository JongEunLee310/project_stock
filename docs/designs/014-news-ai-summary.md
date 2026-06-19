# 014: 뉴스 AI 요약

## 목적

수집된 뉴스 원문을 LLM이 구조화된 JSON으로 요약하여 `news_items`에 저장한다.
긍정/부정 요인을 분리하고 영향도를 분류한다.

## DB 변경

`news_items` 테이블에 컬럼 추가:

| 컬럼 | 타입 | 설명 |
|---|---|---|
| positive_factors | Text, nullable | JSON 배열 문자열 — 긍정 요인 목록 |
| negative_factors | Text, nullable | JSON 배열 문자열 — 부정 요인 목록 |

기존 컬럼 `summary`, `sentiment`, `impact_level` 재사용.

## AI 응답 스키마 (Pydantic)

```
class NewsSummaryResult(BaseModel):
    summary: str                                              # 1~3문장 요약
    positive_factors: list[str]                              # 긍정 요인
    negative_factors: list[str]                              # 부정 요인
    impact_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"]
```

## 프롬프트

```
app/adapters/llm/prompts/news_summary.py
  build_news_summary_messages(title: str, body: str) -> list[LLMMessage]
```

## 서비스

```
class NewsAnalysisService:
    def __init__(self, db: Session, llm_client: LLMClient)
    def summarize(self, news_item_id: int) -> NewsSummaryResult
```

- `LLMClient.complete_json(messages, NewsSummaryResult)` 호출
- Pydantic 검증 실패 시 `news_items` 미업데이트, 예외 전파
- 성공 시 `summary`, `sentiment`, `impact_level`, `positive_factors`, `negative_factors` 업데이트

## 의존성

Issue #13 (LLM Adapter) 완료 후 진행
