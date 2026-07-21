# Codex Handoff Task

## Source Issue

BE #350 — 판단 CRUD + 확정(activate) 라이프사이클 API. Epic #347. ADR-016.

## Task Summary

#349에서 만든 6테이블 모델 위에, 판단 기록의 생성(중첩 근거·위험·재검토 트리거 포함)·
상세 조회·초안 수정·확정(activate) API를 구현한다. 요약(overview)·재검토 큐·목록 필터
확장은 이 태스크 범위가 아니다(후속 #351/#352).

## Goal

- `POST /api/v1/decision-logs` 가 본문 + 중첩 `evidence`/`risks`/`review_triggers` +
  `supporting_reasons`/`counter_arguments`(문자열 배열)를 받아 DRAFT 판단과 부속 레코드를
  생성한다.
- `GET /api/v1/decision-logs/{id}` 가 본문 + 중첩(evidence·risks·review_triggers·snapshots)을
  담은 상세를 반환한다.
- `PATCH /api/v1/decision-logs/{id}` 는 `DRAFT` 상태에서만 허용하고, 그 외 상태면 409
  `DECISION_LOG_INVALID_STATE`.
- `POST /api/v1/decision-logs/{id}/activate` 가 확정 동작(설계 §4.4)을 수행한다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/348-decision-log-redesign.md` §4(API)·§5(시그니처)·§6(에러)이며 반드시
그대로 따른다. ADR-016 §4~§7도 참조. 요지:

- 와이어 컨벤션: snake_case, 시각 `UtcDatetime`, 공통 엔벨로프 `ApiResponse`/`success`/
  `paginated`. 소유권 `user_id`, 전 엔드포인트 `get_current_user`.
- 페이지네이션은 기존 `app/core/pagination.py`의 `PaginationParams`(offset 기반)를 쓴다.
  설계문서의 `cursor` 표기는 무시하고 기존 offset 규약을 따른다.
- `supporting_reasons`/`counter_arguments`(문자열 배열)는 서버에서 `decision_evidence`
  (`relationship=SUPPORTING` / `CONTRADICTING`, 문자열을 `title`에 저장)로 정규화한다.
  구조화 `evidence` 입력과 병존한다(둘 다 올 수 있음).
- `activate` 동작(설계 §4.4): 상태 `DRAFT → ACTIVE`, `activated_at`·`decided_at` 스탬프,
  `DATE` 재검토 트리거의 `scheduled_at` 확정·`status=PENDING`, 요청에 담긴 `snapshots`를
  `decision_snapshots`로 저장. 이미 `DRAFT`가 아니면 409 `DECISION_LOG_INVALID_STATE`.
  1차에서 서버측 자동 스냅샷 조회(가격·포트폴리오 등 외부 도메인 조회)는 넣지 않는다 —
  요청이 제공한 스냅샷만 저장한다(자동 수집은 2차).
- 확정 후 본문 핵심 필드(target·decision_type·thesis·rationale 등) 수정은 막는다(PATCH가
  DRAFT 전용이므로 자연히 차단됨).

## Implementation Scope

- `app/domains/decision_logs/schema.py` — 중첩 입력/응답 스키마 추가:
  `DecisionEvidenceInput`, `DecisionRiskInput`, `DecisionReviewTriggerInput`,
  `DecisionSnapshotInput`, 확장된 `DecisionLogCreate`, `DecisionActivateRequest`,
  `DecisionLogDetailResponse`(본문 + 중첩), 중첩 응답 항목 스키마. 기존 `DecisionLogResponse`,
  `DecisionLogUpdate`는 유지·확장.
- `app/domains/decision_logs/repository.py` — 중첩 생성, 상세 조회(부속 로딩), activate용
  스냅샷/트리거 기록 메서드.
- `app/domains/decision_logs/service.py` — `create_decision`(정규화 포함),
  `get_decision`(상세), `update_draft`(DRAFT 가드), `activate`(§4.4). 시그니처는 설계 §5.
- `app/api/v1/endpoints/decision_logs.py` — `POST /activate` 라우트 추가, 상세 응답 모델
  교체, 기존 라우트 유지.
- `app/core/error_codes.py` — `DECISION_LOG_INVALID_STATE` 추가.
- `tests/test_decision_logs.py` — 신규 동작 테스트 추가(아래).

## Out of Scope

- `GET /decision-logs/overview`(#351), `GET /decision-logs/review-queue`·목록 필터
  확장(#352), `POST /{id}/revise`·`POST /{id}/reviews`(2차).
- 서버측 자동 스냅샷 수집, 이벤트/가격 트리거 감시, Alert 연동, 자동 근거 연결.
- 다른 도메인, FE.
- 기존 `GET /decision-logs/stats`는 이 태스크에서 **건드리지 말고 그대로 둔다**(overview
  도입 시 #351에서 정리).

## Protected Files

없음.

## Requirements

- 필수 입력: `target`(type+id), `decision_type`. 나머지 optional(설계 §4.2).
- `target`은 `{type, id, label?}` 형태 입력을 받아 모델의 `target_type`/`target_id`/`symbol`로
  매핑한다(`type=SYMBOL`이면 `symbol=id`도 채움).
- 잘못된 enum·형식은 422(기존 `VALIDATION_ERROR`). 없음 404 `DECISION_LOG_NOT_FOUND`,
  타인 403 `DECISION_LOG_FORBIDDEN`, 상태 위반 409 `DECISION_LOG_INVALID_STATE`.
- 생성은 단일 트랜잭션으로 본문 + 부속을 함께 커밋한다.

## Test Requirements

- 중첩 생성 라운드트립: evidence(SUPPORTING/CONTRADICTING)·risks·review_triggers가 저장·
  조회되는지. `supporting_reasons`/`counter_arguments`가 evidence로 정규화되는지.
- 상세 조회가 중첩을 포함하는지.
- PATCH가 DRAFT에서 성공, ACTIVE에서 409인지.
- activate가 상태 전이·타임스탬프·DATE 트리거·요청 스냅샷 저장을 수행하는지, 비-DRAFT
  activate가 409인지.
- 소유권(타인 접근 403) 유지.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

설계문서·ADR은 정본. 계약과 어긋나면 설계를 따르되, 불가피한 이탈은 설계문서에 한 줄
주석으로 사유를 남긴다.

## ADR Need

불필요(ADR-016 구현).

## Failure Record Need

불필요.

## Risk Level

Medium — 다중 테이블 트랜잭션·라이프사이클 가드. 스키마는 #349에서 확정됨.

## Expected Output

- 변경 파일: schema/repository/service/endpoint/error_codes + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/348-decision-log-redesign` 유지(새 브랜치 금지). 한국어 `feat:` 커밋,
  `#350` 참조.
