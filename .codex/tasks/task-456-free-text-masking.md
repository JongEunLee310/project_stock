# Codex Handoff Task

## Source Issue

#456 — [BE] 클라우드 LLM 자유 텍스트 민감정보 마스킹(Q&A·Decision Assist) (에픽 #438)

## Task Summary

클라우드 LLM으로 나가는 사용자 작성 자유 텍스트에서 개인식별 정보와 개인 맥락의 보유 수량·금액을
자리표시자로 가린다. 마스킹은 각 호출부가 아니라 `LLMGateway`의 클라우드 경로에서 `PrivacyGate`가
강제한다. 두 API 응답에 가린 범주(`masked_categories`)를 추가한다.

## Goal

- 클라우드 client가 받는 메시지에 선언된 자유 텍스트 필드의 민감 정보 원문이 없다.
- 공개 사실 속 금액·수량("애플-브로드컴 300억 달러 계약")은 가려지지 않는다.
- 로컬 경로(로컬 LLM 라우팅, 로컬 임베딩, Obsidian 노트)는 원문을 그대로 쓴다.
- 두 API 응답에 `masked_categories`가 추가된다(기존 필드 불변).

## Background

- 결정: `docs/decisions/ADR-019-free-text-masking-at-cloud-boundary.md`(ADR-009 보완)
- 설계 정본: `docs/designs/456-free-text-masking.md`. 범주(§1), 개인 맥락 판정(§2), 오탐 방지(§3),
  컴포넌트 시그니처(§4), 계약(§5), 테스트(§6)를 그대로 따른다. **반드시 먼저 읽는다.**
- 현재 코드
  - `CloudSafePayload`, `ResearchQASnapshot`, `DecisionAssistSnapshot`, `PrivacyGate`:
    `app/adapters/llm/privacy.py`
  - 클라우드 경로: `LLMGateway.complete_json`(`app/adapters/llm/gateway.py:59`)과
    `_verify_with_cloud`(`gateway.py:177`). 사전 escalation 판단의 `guard`(`gateway.py:69-90`)는
    판정용이므로 바꾸지 않는다.
  - 응답 캐시 키 생성: `self.response_cache.build_key(task_type, safe_payload, ...)`(complete_json 안)
  - `LLMCompletionResult`: `gateway.py:25`
  - Q&A 서비스: `app/domains/rag/service.py`, 스키마 `app/domains/rag/schema.py`, Obsidian 렌더링
    `app/adapters/obsidian/writer.py`
  - Decision Assist: `app/domains/decision_logs/assist_service.py`, 스키마
    `app/domains/decision_logs/schema.py`(`DecisionAssistResponse`)
- 정규식은 표준 라이브러리 `re`만 쓴다. 의존성을 추가하지 않는다. `uv add`, `uv sync`, 네트워크,
  `git fetch`, docker 명령을 하지 않는다.

## Implementation Scope

1. `app/adapters/llm/masking.py`: `MaskCategory`, `MaskResult`, `mask_sensitive_text`(설계 §1~§3, §4.1)
2. `privacy.py`
   - `CloudSafePayload.free_text_fields: ClassVar[tuple[str, ...]] = ()`와 선언 검증(설계 §4.2)
   - `ResearchQASnapshot.free_text_fields = ("question",)`
   - `DecisionAssistSnapshot.free_text_fields = ("thesis", "rationale", "memo")`
   - `PrivacyGate.mask(payload) -> tuple[CloudSafePayload, frozenset[MaskCategory]]`(설계 §4.3)
3. `gateway.py`
   - 직접 클라우드 호출과 클라우드 검증 경로에서 `guard` 다음 `mask`를 적용하고, 마스킹된 payload만
     client 메시지와 캐시 키에 쓴다.
   - `LLMCompletionResult.masked_categories` 추가. 캐시 적중 경로와 로컬 경로(빈 집합)도 채운다.
   - 클라우드 검증 경로에서 가린 범주는 최종 결과에 합친다.
4. Q&A
   - `ResearchAnswer.masked_categories: list[MaskCategory] = []`. LLM을 호출했을 때는
     `completion.masked_categories`를 선언 순서로 정렬해 담는다. 근거 0건이나 LLM 실패 시에는 빈 목록.
   - 질문 임베딩은 원문 그대로다(변경 없음을 테스트로 확인).
   - Obsidian 노트: 질문 원문 유지, frontmatter에 `masked_categories` 추가(빈 목록이면 `[]`).
5. Decision Assist: `DecisionAssistResponse`에 `masked_categories` 추가. 성공 시 결과 값, 실패 시 빈 목록.
6. 문서
   - `docs/api/frontend-api-spec.md`에 두 응답 필드와 `MaskCategory` 값 추가
   - 설계 438 §5.1에 `masked_categories` 한 줄 추가(설계 456 참조)
   - 설계 456의 "가정" 값을 바꿨다면 그 문서에 반영한다.
7. 로컬 리뷰 체크리스트에 항목 추가는 하지 않는다(`docs/harness/`는 protected). orchestrator가 판단한다.

## Out of Scope

- 사람 이름·주소 판별, 로컬 LLM 판별
- 다른 `CloudSafePayload`(구조화 projection)의 변경
- FE
- 마이그레이션

## Protected Files

없음. `docs/decisions/`와 `docs/harness/`는 수정하지 않는다.

## Requirements

- 원문과 자리표시자의 대응을 저장하거나 로그에 남기지 않는다. 범주 이름만 로그에 남긴다.
- `CloudSafePayload`는 frozen이므로 `model_copy(update=...)`로 사본을 만든다.
- 모든 공개 함수에 타입 주석을 단다.
- 주석은 이유가 분명하지 않은 곳에만 최소한으로 쓴다.

## Test Requirements

설계 §6 표를 모두 구현한다. 특히 다음은 반드시 포함한다.

- 양성: "삼성전자 300주를 평단 7만 원에 샀는데 지금 리스크는?" → 수량·금액 가림, `QUANTITY`·`AMOUNT`
- 음성: "애플-브로드컴 300억 달러 계약 내용은?", "PER 30배 이하 종목의 3분기 실적은?", "자사주
  1,000만 주 소각 계획은?" → 그대로
- 개인식별: 이메일, `010-1234-5678`, `+82 10 1234 5678`, `900101-1234567`, `1234-5678-9012-3456`,
  "계좌 123-456789-01-012"
- 영어: "I bought 100 shares at $180, should I worry?" → 수량·금액 가림
- 게이트웨이: Mock client가 받은 메시지 문자열에 원문 금액·연락처가 없음(직접 경로, 클라우드 검증
  경로), 로컬 경로는 원문, 캐시 적중 시 `masked_categories` 동일
- Q&A·Decision Assist API 응답의 `masked_categories`, Obsidian 노트 원문 유지와 frontmatter 범주

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## ADR Need

ADR-019를 orchestrator가 작성했다. 구현 중 ADR과 다르게 해야 하면 멈추고 보고한다.

## Failure Record Need

불필요.

## Risk Level

High — 프라이버시 경계(ADR-009) 변경이다. 사용자가 2026-10-12 마스킹 범위(개인식별 + 보유·거래)와
적용 대상(Q&A + Decision Assist)을 결정했다. 머지 전 사람 리뷰가 필요하다.

## Expected Output

- 현재 브랜치 `feat/456-free-text-masking`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, 가정(특히 정규식 판정 경계), 검증 결과

## Stop Conditions

- 설계·ADR과 다르게 구현해야 하는 상황
- 의존성 추가가 필요한 상황
- 기존 테스트가 이 변경과 무관한 이유로 실패하는 상황
- 샌드박스 권한 부족

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
