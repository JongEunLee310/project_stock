# Codex Handoff Task

## Source Issue

- BE #206 — `NEWS_SUMMARY`·`THESIS_CONFLICT` 경로를 `LLMGateway`로 수렴
- Epic BE #141
- 설계: `docs/designs/078-news-pipeline-completion.md` Part B (§2·§3.4–3.7·§6)
- **선행 태스크: task-142 완료 후 같은 브랜치에서 이어 실행한다.**

## Task Summary

`NewsAnalysisService`·`ThesisAnalysisService`가 `LLMClient`를 직접 주입받는 구조를
`LLMGateway` 기반으로 전환한다. `privacy.py`에 두 경로 전용 `CloudSafePayload` 스냅샷을
추가하고, 프롬프트 파일을 시스템 프롬프트 빌더 함수로 재편하며, `WatchlistAnalysisService`와
잡 레이어에서 게이트웨이를 주입하도록 연결한다. 전환 후 `app/domains/` 안에 `LLMClient`를
직접 주입받는 분석 서비스가 없어야 한다.

## Goal

- `NewsAnalysisService`·`ThesisAnalysisService`·`WatchlistAnalysisService`가 `LLMGateway`를
  주입받는다.
- `app/worker/jobs/analysis.py`에서 `get_llm_client()` 취득이 제거되고 `get_llm_gateway()`로
  대체된다.
- `LLMGateway.complete_json`이 `NewsSummarySnapshot`·`ThesisConflictSnapshot`을 통해 호출되며
  PrivacyGate·라우팅·timeout을 적용받는다.
- 기존 분석 결과(`completion.output`)를 `model_validate`에 연결하는 흐름이 그대로 유지된다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- 현재 `NewsAnalysisService`(`app/domains/news/service.py`)·`ThesisAnalysisService`
  (`app/domains/theses/conflict_service.py`)는 `LLMClient`를 직접 주입받아
  `build_news_summary_messages`·`build_thesis_conflict_messages`로 메시지를 조립한 뒤 호출한다.
  이 경로는 timeout·PrivacyGate·라우팅·실행 메타를 받지 못한다.
- `LLMGateway.complete_json(task_type, payload: CloudSafePayload, schema, system_prompt)`는
  payload를 JSON 사용자 메시지로 스스로 조립한다. `app/adapters/llm/router.py`에
  `NEWS_SUMMARY`·`THESIS_CONFLICT` 두 task 경로가 이미 정의되어 있고 둘 다 `launch=cloud`다.
- `CloudSafePayload`·`SensitivityLevel`·`PrivacyGate`는 `app/adapters/llm/privacy.py`·
  `app/adapters/llm/types.py` 참조.
- Decision DDD: `NewsSummarySnapshot`은 `PUBLIC`, `ThesisConflictSnapshot`은 `AGGREGATED`.
  현재도 직접 호출로 cloud에 전송 중이므로 동작 보존에 해당한다.
- Decision CCC의 기각 대안: 게이트웨이에 메시지 리스트 오버로드 추가 — 게이트웨이의
  "ContextBundle(CloudSafePayload)만 입력" 원칙(§18)을 깨므로 기각됨.
- 실행 메타(provider·model_name) 영속화는 이 태스크 범위 밖이다. `LLMAnalysisRun`은
  `llm_analysis` 도메인 전용이며 변경하지 않는다.
- 이 태스크는 task-142가 완료된 브랜치 위에서 이어 실행된다. task-142 결과물(컬럼 추가·
  migration·ContextBuilder 변경)에 의존하지 않지만 같은 PR로 묶인다.

## Implementation Scope

1. `app/adapters/llm/privacy.py` — `NewsSummarySnapshot`·`ThesisConflictSnapshot` 추가:
   - `NewsSummarySnapshot(CloudSafePayload)`: `title: str`, `body: str`,
     `sensitivity = SensitivityLevel.PUBLIC`.
   - `ThesisConflictSnapshot(CloudSafePayload)`: `thesis_summary: str`,
     `invalidation_conditions: str`, `news_summary: str`, `news_positive_factors: list[str]`,
     `news_negative_factors: list[str]`, `sensitivity = SensitivityLevel.AGGREGATED`.
2. `app/adapters/llm/prompts/news_summary.py` — `build_news_summary_messages`를
   `build_news_summary_system_prompt() -> str`로 교체. 기존 지시문과 JSON Schema 내용은
   유지한다(지시문 수정 금지).
3. `app/adapters/llm/prompts/thesis_conflict.py` — `build_thesis_conflict_messages`를
   `build_thesis_conflict_system_prompt() -> str`로 교체. 기존 지시문과 JSON Schema 내용은
   유지한다(지시문 수정 금지).
4. `app/domains/news/service.py` — `NewsAnalysisService.__init__` 시그니처를
   `(self, db, gateway: LLMGateway)`로 변경. `LLMClient` 직접 호출 제거.
   `gateway.complete_json(LLMTaskType.NEWS_SUMMARY, NewsSummarySnapshot(...),
   NewsSummaryResult, build_news_summary_system_prompt())` 방식으로 교체.
   `completion.output`을 기존 `model_validate`에 연결.
5. `app/domains/theses/conflict_service.py` — `ThesisAnalysisService.__init__` 시그니처를
   `(self, db, gateway: LLMGateway)`로 변경. 동일 방식으로 교체.
6. `app/domains/analysis/service.py` — `WatchlistAnalysisService.__init__` 시그니처를
   `(self, db, gateway: LLMGateway, news_adapter)`로 변경. 두 하위 서비스 생성 시
   `gateway` 주입.
7. `app/worker/jobs/analysis.py` — `get_llm_client()` 취득 제거, `get_llm_gateway()`로
   `WatchlistAnalysisService` 생성.
8. 영향받는 테스트 갱신 — 기존 테스트가 `MockLLMClient` 직접 주입에 의존하면
   `MockLLMClient`로 조립한 실제 `LLMGateway`(예: `LLMGateway({CLOUD: mock, LOCAL: mock})`)
   주입으로 교체한다. 코드베이스는 sync이므로 `AsyncMock`은 사용하지 않는다. 요약·충돌 분석
   결과가 기존과 동일하게 저장되는지 검증하는 단언을 유지·추가한다.

## Out of Scope

- `app/adapters/llm/gateway.py`·`router.py`·`base.py` 변경.
- `app/domains/llm_analysis/` 변경.
- 실행 메타(provider·model_name) 영속화.
- 프롬프트 지시문(instruction 텍스트) 내용 변경.
- `LLMAnalysisRun` 생성·조회 로직 변경.

## Protected Files

- `app/adapters/llm/gateway.py` — 변경 금지.
- `app/adapters/llm/router.py` — 변경 금지.
- `app/adapters/llm/base.py` — 변경 금지.
- `app/domains/llm_analysis/` — 변경 금지.
- `alembic/versions/` — 변경 금지.

## Requirements

- 전환 후 `app/domains/` 안의 분석 서비스(`NewsAnalysisService`·`ThesisAnalysisService`)가
  `LLMClient`를 직접 주입받지 않는다.
- `completion.output`을 `model_validate`에 연결하는 기존 흐름이 보존된다.
- `NewsSummarySnapshot`·`ThesisConflictSnapshot`의 `sensitivity` 분류가 DDD와 일치한다
  (PUBLIC·AGGREGATED).
- 타입 힌트 완전성 (mypy 통과 수준).
- 주석은 WHY가 명확하지 않을 때만 최소한으로.

## Test Requirements

- 신규 또는 갱신: `NewsAnalysisService`·`ThesisAnalysisService`가 게이트웨이 경유로도 기존과
  동일한 결과를 저장하는지 검증.
- 갱신: `MockLLMClient` 직접 주입에 의존하는 기존 테스트를 `MockLLMClient`로 조립한
  `LLMGateway` 주입으로 교체.
- 기존 테스트 전부 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

설계 078이 이 PR에 동봉된다. 지침서·ADR 갱신 불필요.

## ADR Need

없음 — 설계 078 §7 참조.

## Failure Record Need

없음 — 계획된 경로 수렴이며 결함 마감이 아니다.

## Risk Level

중간. 두 서비스의 LLM 호출 경로가 바뀌므로 기존 테스트 갱신이 수반된다. 단, 게이트웨이·
라우터·프롬프트 지시문 내용은 변경되지 않으므로 LLM 입출력 계약은 그대로다.

## Expected Output

- 수정: `app/adapters/llm/privacy.py`, `app/adapters/llm/prompts/news_summary.py`,
  `app/adapters/llm/prompts/thesis_conflict.py`, `app/domains/news/service.py`,
  `app/domains/theses/conflict_service.py`, `app/domains/analysis/service.py`,
  `app/worker/jobs/analysis.py`, 영향받는 테스트 파일
- 검증 4종 통과

## Decisions 요약 (설계 078 참조)

- CCC: 전용 CloudSafePayload 스냅샷 + 시스템 프롬프트 빌더 재편 (게이트웨이 메시지 오버로드 기각).
- DDD: `NewsSummarySnapshot`=PUBLIC, `ThesisConflictSnapshot`=AGGREGATED.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
