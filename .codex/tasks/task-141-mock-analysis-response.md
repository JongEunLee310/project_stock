# Codex Handoff Task

## Source Issue

- BE #203 — [LLM] DEFAULT_MOCK_RESPONSES에 LLMAnalysisResult 항목 누락
- Epic BE #141, #202와 같은 스모크 테스트에서 발견

## Task Summary

`app/adapters/llm/mock.py`의 `DEFAULT_MOCK_RESPONSES`에 `LLMAnalysisResult` 유효 응답을
추가하고, 기본 mock 응답이 대응 스키마로 검증되는지 고정하는 회귀 테스트를 추가한다.
데이터 추가만 있는 마감이라 별도 설계 문서는 없다(구조 결정 없음).

## Background

- `MockLLMClient.complete_json`은 `self.responses.get(schema.__name__, ...)`로 응답을
  조회한다. `LLMAnalysisService`는 `LLMAnalysisResult` 스키마를 쓰는데 기본 응답 dict에
  해당 키가 없어 `{}`가 반환되고 pydantic 검증이 8건 실패한다.
- `LLMAnalysisResult` 필드: `summary: str`, `risk_level: RiskLevel(LOW|MEDIUM|HIGH)`,
  `suggested_action: SuggestedAction(buy_watch|hold|trim_watch|avoid|need_more_data)`,
  `reasons/watch_points/counter_arguments/data_limitations: list[str]`,
  `confidence: float(0~1)`.
- 참고 값: `tests/test_llm_analysis_service.py`의 `VALID_ANALYSIS_RESPONSE`.

## Implementation Scope

1. `app/adapters/llm/mock.py` — `DEFAULT_MOCK_RESPONSES`에 `"LLMAnalysisResult"` 항목 추가.
   기존 항목들과 같은 mock 톤의 유효 값(`risk_level="LOW"`, `suggested_action="hold"`,
   `confidence` 0~1 사이 등).
2. 회귀 테스트 — `DEFAULT_MOCK_RESPONSES["LLMAnalysisResult"]`가
   `LLMAnalysisResult.model_validate`를 통과하는지 검증. 기존 mock/factory 테스트 파일 중
   적절한 위치에 추가(새 파일 강제 아님).

## Out of Scope

- `MockLLMClient` 조회 로직 변경 (미등록 스키마 fallback 동작 변경 금지)
- 다른 기본 응답 항목 값 변경
- 서비스·게이트웨이·factory 변경

## Protected Files

- `app/domains/llm_analysis/schema.py` — 변경 금지
- `app/adapters/llm/gateway.py`·`factory.py` — 변경 금지

## Requirements

- 타입 힌트 완전성 (mypy 통과 수준)
- 주석 불필요 (데이터 추가)

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

없음.

## ADR Need / Failure Record Need

없음 — 데이터 누락 마감이며 #202의 FAILURE-002와 달리 재사용할 패턴이 아니다.

## Risk Level

낮음. dict 항목 추가와 테스트 1건.

## Expected Output

- 수정: `app/adapters/llm/mock.py`, 테스트 1건 추가
- 검증 4종 통과
