# BE 설계: 판단 작성 AI 보조 endpoint — 이슈 #356

상태: **계약 확정(Frozen)** — 2026-07-21. 에픽 BE #347. FE 소비 `project_stock_frontend#250`.
판단 기록 재설계([[348-decision-log-redesign]])의 추가 스코프.

이 문서는 판단 작성 폼의 AI 보조를 위한 비영속 LLM 엔드포인트 계약을 스켈레톤 수준으로
확정한다. 리터럴 출처는 사용자 제공 설계 지침(§7·§16·§23)과 기존 LLM 인프라
(`app/adapters/llm/`)다.

## 배경

디자인 이미지(`decision-log.png`)의 작성 폼은 순수 수기 입력이다. 사용자 지시로 여기에
AI agent 보조를 추가한다. 원칙(ADR-016 §7): **AI는 판단을 대신하지 않고 구조화·검증만
돕는다.** 제안은 반환만 하고 저장하지 않으며, 저장은 FE에서 사용자가 확인([적용])한 뒤
기존 create/activate 흐름으로 이뤄진다.

## 1. API 계약

| Method · Path | 책임 | Auth | 영속 |
| --- | --- | --- | --- |
| `POST /api/v1/decision-logs/assist` | 판단 초안에 대한 AI 보조 제안 | Required | No |

와이어 컨벤션은 기존과 동일(snake_case, `ApiResponse`/`success`). 소유권은 요청 사용자
기준이나 DB 접근이 없으므로 리소스 소유권 검사는 없다(인증만).

### 1.1 요청 스키마 `DecisionAssistRequest`

- `target`: `{type: TargetType, id: str}` (필수).
- `decision_type`: `DecisionType | None`.
- `thesis`: `str | None`.
- `rationale`: `str | None`.
- `memo`: `str | None` (거친 자유 메모).

### 1.2 응답 스키마 `DecisionAssistResponse`

- `structured_thesis`: `str | None` — 정리된 가설 제안.
- `structured_rationale`: `str | None` — 정리된 판단 이유 제안.
- `counter_arguments`: `list[str]` — 반대 근거 후보.
- `risk_candidates`: `list[{type: str, reason: str}]` — 인지 위험 점검 후보(type은 위험 태그
  권장 집합 값, 미지 값 허용).
- `bias_candidates`: `list[{type: str, reason: str}]` — 행동 편향 점검 후보(FOMO 등).
  **확정 진단이 아니라 점검 후보**임을 필드 의미로 고정한다.
- `vague_flags`: `list[{quote: str, suggestion: str}]` — 모호 표현과 보완 제안.

전 필드는 제안이며 비어 있을 수 있다(부분 실패·해당 없음 시 빈 목록/`null`).

## 2. LLM 배선

기존 게이트웨이(`app/adapters/llm/gateway.py`의 `LLMGateway.complete_json(task_type,
payload, schema, system_prompt)`)를 재사용한다.

- `app/adapters/llm/types.py` — `LLMTaskType.DECISION_ASSIST` 추가.
- `app/adapters/llm/privacy.py` — `DecisionAssistSnapshot(CloudSafePayload)` 추가. 클라우드로
  나가는 필드는 사용자 초안 텍스트로 한정(`decision_type`·`thesis`·`rationale`·`memo`·
  `target_type`·`symbol`). 종목 식별자 외 시스템 내부 식별자·타 사용자 데이터는 싣지 않는다.
- LLM 응답 파싱용 결과 모델(gateway `schema` 인자)로 `DecisionAssistResult(BaseModel)`를
  두고, 응답 스키마(`DecisionAssistResponse`)로 매핑한다.
- `app/adapters/llm/prompts/decision_assist.py` — system prompt 빌더 + `PROMPT_VERSION`.
  프롬프트는 "판단을 대신 확정하지 말 것, 편향은 점검 후보로만, 사용자 텍스트 근거로만"을
  명시한다.
- LLM router가 `DECISION_ASSIST`를 provider로 resolve하도록 매핑을 추가한다(기존 task_type
  라우팅 설정과 동일 위치).

## 3. Service

`DecisionAssistService`(신규, `app/domains/decision_logs/` 또는 `llm_analysis` 배치는 구현
판단) — 책임 한 줄:

- `assist(user_id, DecisionAssistRequest) -> DecisionAssistResponse` — CloudSafe 스냅샷 구성 →
  `gateway.complete_json(DECISION_ASSIST, snapshot, DecisionAssistResult, prompt)` 호출 →
  결과를 응답 스키마로 매핑. LLM 예외는 시스템 경계에서 잡아 부분/안전 실패로 변환.

Repository는 없다(비영속). DB 기록·감사 이력 없음.

## 4. CloudSafe 경계 (ADR-009)

사용자 판단 초안 텍스트를 클라우드 LLM에 보내는 새 경로다. `DecisionAssistSnapshot`은
`CloudSafePayload`를 상속해 privacy 게이트를 통과하며, 화이트리스트 필드만 직렬화한다.
초안 텍스트 자체는 보조의 입력이므로 전송 대상이지만, 사용자 계정·내부 ID·타 도메인
스냅샷은 싣지 않는다. 이 경계 판단은 ADR-009의 적용이다(신규 ADR 불필요, §6 참조).

## 5. 에러·실패 처리

- 인증 실패 401(기존). 입력 검증 422(기존 `VALIDATION_ERROR`).
- LLM 호출 실패는 500이 아니라, 가능한 부분 결과 또는 빈 제안으로 안전하게 반환하는 것을
  기본으로 한다(보조는 실패해도 작성 흐름을 막지 않아야 한다). 완전 실패 시의 코드·메시지는
  구현에서 기존 LLM 실패 처리 관례를 따른다.

## 6. ADR 필요 여부

신규 ADR 불필요. 두 기존 결정의 적용이다.

- ADR-016 §7이 "AI는 판단을 대신하지 않고 구조화·검증만 돕는다, 제안은 확인 후 저장"을
  이미 원칙으로 고정했다. 본 엔드포인트는 그 구현이다.
- ADR-009가 클라우드 데이터 경계(CloudSafe projection)를 이미 정했다. 본 엔드포인트는 새
  `CloudSafePayload` 하위 타입으로 그 경계를 적용한다.

새로운 아키텍처 방향 선택이 아니라 계획된 원칙의 구현이므로 설계문서로 충분하다.

## 7. 범위 밖(후속)

- 관련 근거 자동 연결(Signal/Research/Topic)·복기 요약(2차 이후).
- 편향 확정 진단·자동 판단 확정(원칙상 금지, 도입 안 함).
- 보조 결과의 영속화·감사 이력(현재 비영속 유지).
- FE UI([적용][수정][무시])는 FE 트랙(`project_stock_frontend#250`).
