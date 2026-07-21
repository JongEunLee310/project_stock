# Codex Handoff Task

## Source Issue

BE #356 — 판단 작성 AI 보조 endpoint (LLM 연동·CloudSafe·비영속). Epic #347.

## Task Summary

판단 작성 폼의 AI 보조를 위한 비영속 LLM 엔드포인트 `POST /api/v1/decision-logs/assist`를
구현한다. 사용자 초안을 받아 4종 제안(반대 근거 후보·핵심 판단 구조화·인지 위험/편향 점검
후보·모호 표현 감지)을 반환한다. 저장하지 않는다.

## Goal

- `POST /api/v1/decision-logs/assist`가 `DecisionAssistRequest`를 받아
  `DecisionAssistResponse`를 반환한다.
- 기존 LLM 게이트웨이를 재사용해 신규 `LLMTaskType.DECISION_ASSIST`로 호출한다.
- DB 기록 없음(비영속). LLM 실패가 작성 흐름을 막지 않도록 안전 처리.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/356-decision-assist.md`이며 반드시 먼저 읽고 그대로 따른다. 원칙은
ADR-016 §7(AI는 판단을 대신하지 않고 구조화·검증만, 제안은 확인 후 저장)과 ADR-009
(CloudSafe 경계)다.

기존 인프라(그대로 재사용):
- `app/adapters/llm/gateway.py` — `LLMGateway.complete_json(task_type, payload, schema,
  system_prompt)`. 사용 예시는 `app/domains/llm_analysis/service.py`(`gateway.complete_json(...)`).
- `app/adapters/llm/types.py` — `LLMTaskType` enum.
- `app/adapters/llm/privacy.py` — `CloudSafePayload` 및 하위 스냅샷들.
- `app/adapters/llm/prompts/` — task별 프롬프트 빌더(`analysis.py`·`news_summary.py` 참고).
- LLM router 설정 — `task_type`을 provider로 resolve(기존 task_type이 등록된 곳과 동일 위치에
  `DECISION_ASSIST` 매핑 추가).

## Implementation Scope

- `app/adapters/llm/types.py` — `LLMTaskType.DECISION_ASSIST` 추가.
- `app/adapters/llm/privacy.py` — `DecisionAssistSnapshot(CloudSafePayload)` 추가. 화이트리스트
  필드: `target_type`, `symbol`(nullable), `decision_type`(nullable), `thesis`, `rationale`,
  `memo`. 내부 ID·타 사용자·타 도메인 스냅샷은 싣지 않는다.
- `app/adapters/llm/prompts/decision_assist.py` — system prompt 빌더 + `PROMPT_VERSION`.
  프롬프트에 "판단을 대신 확정 금지, 편향은 점검 후보로만, 사용자 텍스트 근거로만, 모호
  표현엔 보완 제안" 명시.
- LLM router 매핑에 `DECISION_ASSIST` 추가(기존 task_type 라우팅과 동일 위치·방식).
- `app/domains/decision_logs/schema.py`(또는 별도 assist schema 모듈) — `DecisionAssistRequest`,
  `DecisionAssistResponse`, 그리고 gateway `schema` 인자용 `DecisionAssistResult`(BaseModel).
  설계 §1.1·§1.2 필드 그대로.
- `app/domains/decision_logs/`(신규 `assist_service.py` 또는 기존 service에 추가) —
  `DecisionAssistService.assist(user_id, DecisionAssistRequest) -> DecisionAssistResponse`.
  CloudSafe 스냅샷 구성 → `gateway.complete_json(DECISION_ASSIST, snapshot,
  DecisionAssistResult, build_decision_assist_system_prompt())` → 응답 매핑.
- `app/api/v1/endpoints/decision_logs.py` — `POST /assist` 라우트. 리터럴 경로이므로
  `/{decision_log_id}` 보다 먼저 등록한다.
- 테스트(아래).

## Out of Scope

- 관련 근거 자동 연결·복기 요약·영속화·감사 이력.
- 편향 확정 진단·자동 판단 확정(원칙상 금지).
- FE UI(`project_stock_frontend#250`).
- 다른 도메인.

## Protected Files

없음. LLM 어댑터(`app/adapters/llm/`)는 신규 task_type·payload·prompt·router 매핑 추가만
하고 기존 task 동작을 바꾸지 않는다.

## Requirements

- 비영속: DB 접근·기록 없음. Repository 만들지 않는다.
- Auth 필수(`get_current_user`). 리소스 소유권 검사는 없음(DB 리소스 없음).
- CloudSafe: `DecisionAssistSnapshot`은 `CloudSafePayload` 상속, 화이트리스트 필드만.
- LLM 실패는 시스템 경계에서 처리해 작성 흐름을 막지 않는다. 완전 실패 시 기존 LLM 실패
  처리 관례를 따르되, 가능하면 빈 제안으로 안전 반환.
- 응답 필드는 제안이며 비어 있을 수 있다(빈 목록/null 허용).

## Test Requirements

- gateway를 스텁/모의로 두고, assist가 4종 제안을 응답 스키마로 매핑하는지.
- CloudSafe 스냅샷이 화이트리스트 필드만 포함(내부 ID 누출 없음)하는지.
- 인증 없으면 401, 잘못된 입력 422.
- LLM 예외 시 안전 처리(작성 흐름 비차단) 경로.
- 기존 LLM task 동작이 깨지지 않는지(회귀).

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

`docs/designs/356-decision-assist.md`가 정본이며 이미 커밋됨. ADR 불필요(ADR-009·ADR-016
적용, 설계 §6에 근거 명시). Failure Record 불필요.

## ADR Need

불필요. 설계 §6 참조.

## Failure Record Need

불필요.

## Risk Level

Medium — 새 LLM task 경로·CloudSafe 경계. 기존 게이트웨이 재사용이라 인프라 신규 구축은
없으나, privacy 화이트리스트와 실패 처리가 중요하다.

## Expected Output

- 변경 파일: llm types/privacy/prompt/router 매핑, decision_logs schema·assist service·endpoint,
  테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/356-decision-assist` 유지(새 브랜치 금지). 한국어 `feat:` 커밋, `#356`
  참조.
