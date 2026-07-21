# Codex Handoff Task

## Source Issue

BE #352 — 재검토 예정(review-queue) API + 목록 필터 확장 + 목록 projection 경량화.
Epic #347. ADR-016. 판단 기록 1차 마지막.

## Task Summary

`GET /api/v1/decision-logs/review-queue`를 추가하고, 목록(`GET /decision-logs`)에 필터를
확장한다. 동시에 목록 응답을 설계 §4.3의 경량 `DecisionLogListItem`으로 교체해 현재의
행별 중첩 로딩(N+1)을 제거한다.

## Goal

- `GET /api/v1/decision-logs/review-queue`가 재검토가 도래한 판단 목록을 반환한다.
- `GET /api/v1/decision-logs`가 `target_type`·`symbol`·`decision_type`·`status`·`risk_type`·
  `review_due_before` 필터를 지원한다.
- 목록·review-queue 응답이 `DecisionLogListItem`(경량)이며, 페이지 데이터를 **행당 개별
  쿼리 없이**(배치 로딩) 구성한다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/348-decision-log-redesign.md` §4.1(필터)·§4.3(`DecisionLogListItem`),
ADR-016. 소유권 `user_id`, `get_current_user`, 공통 엔벨로프, offset 페이지네이션.

현재 목록은 `DecisionLogResponse`(중첩 evidence/risks/triggers 포함)를 행마다 만들고,
`_to_response`가 판단마다 evidence·risks·triggers를 개별 쿼리로 로딩해 N+1이 발생한다.
이 태스크에서 목록·review-queue는 경량 projection으로 바꾼다. 단건 상세(`GET /{id}`)는
기존대로 중첩 포함 `DecisionLogDetailResponse`를 유지한다.

## Implementation Scope

- `app/domains/decision_logs/schema.py` — `DecisionLogListItem` 추가(설계 §4.3):
  `id`, `target`(`{type,id,label}`), `decision_type`, `summary`, `risks`(str[]),
  `confidence_level`, `status`, `review_at?`(`UtcDatetime`), `created_at`. `decision_label`은
  서버가 내려주지 않는다(FE 표시 계층이 enum→라벨 매핑, C8). 필터용 쿼리 파라미터 모델
  또는 시그니처.
- `app/domains/decision_logs/repository.py` —
  - 목록에 필터 적용(`target_type`·`symbol`·`decision_type`·`status`, `risk_type`는
    `decision_risks` EXISTS/조인, `review_due_before`는 PENDING `DATE` 트리거
    `scheduled_at <= review_due_before` EXISTS).
  - `list_review_due(user_id, now)` — PENDING `DATE` 트리거 `scheduled_at <= now`를 가진
    판단(중복 제거), 정렬은 가까운 재검토 순(`scheduled_at` 오름차순) 권장.
  - 페이지 판단들의 `risks`와 `review_at`(가장 이른 PENDING `DATE` 트리거 `scheduled_at`)를
    **한 번의 쿼리씩** 배치 로딩하는 헬퍼(판단 id 목록 → {id: [...]}) — 행별 쿼리 금지.
- `app/domains/decision_logs/service.py` —
  - `list_decisions`가 필터를 받아 `(list[DecisionLogListItem], total)` 반환. 배치 로딩으로
    조립. `summary`는 `rationale`을 잘라 만든다(예: 앞 200자, 규칙은 상수화).
  - `get_review_queue(user_id) -> (list[DecisionLogListItem], total)`.
- `app/api/v1/endpoints/decision_logs.py` —
  - `GET /review-queue` 라우트(리터럴 경로이므로 `/{decision_log_id}` 보다 먼저 등록).
  - 기존 `GET ""` 목록에 필터 쿼리 파라미터 추가, 응답 모델을
    `ApiResponse[list[DecisionLogListItem]]`로 교체.
- `tests/test_decision_logs.py`(+ 필요 시 `tests/test_api_contract.py`) — 필터·review-queue·
  경량 응답 형태 테스트.

## Out of Scope

- 복기·버전·이벤트/가격 트리거 감시·자동 근거 연결(2차). review-queue는 `DATE` 트리거만.
- 상태를 `REVIEW_DUE`로 자동 전이시키는 스케줄러/잡(2차). 이 태스크는 조회 시점 계산만 한다.
- overview(#351, 완료), 단건 상세 중첩(#350, 유지).
- 커서 페이지네이션(기존 offset 유지).
- 다른 도메인, FE.

## Protected Files

없음.

## Requirements

- 모든 조회는 사용자 소유만.
- 잘못된 enum 필터 값은 422.
- 필터는 조합 가능(AND). 미지정 필터는 조건 없음.
- `risk_type`·`review_due_before`는 서브쿼리 EXISTS 또는 조인+distinct로 판단 단위 중복
  제거.
- 목록/review-queue는 페이지 크기와 무관하게 쿼리 수가 상수여야 한다(본문 1 + 총계 1 +
  risks 배치 1 + review_at 배치 1 수준). 행별 반복 쿼리 금지.

## Test Requirements

- 각 필터 단독·조합 동작(`target_type`/`symbol`/`decision_type`/`status`/`risk_type`/
  `review_due_before`).
- review-queue가 due한 DATE 트리거를 가진 판단만, 가까운 순으로 반환.
- 목록 응답이 경량 형태(중첩 evidence/triggers 미포함, `risks`는 문자열 배열, `review_at`
  포함)인지.
- `summary`가 `rationale` 절단으로 채워지는지(긴 rationale 경계).
- 타 사용자 레코드 격리.
- 잘못된 enum 필터 422.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

설계문서 §4.1·§4.3이 정본. 목록 응답을 `DecisionLogListItem`으로 확정하는 것은 설계와
일치(이전 단계에서 임시로 무거운 응답을 썼던 것을 바로잡음). 추가 문서 변경 불필요.

## ADR Need

불필요(ADR-016 구현).

## Failure Record Need

불필요.

## Risk Level

Low~Medium — 읽기 전용이나 필터·배치 로딩 정확성이 중요. 계약·스키마는 확정됨.

## Expected Output

- 변경 파일: schema/repository/service/endpoint + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/348-decision-log-redesign` 유지(새 브랜치 금지). 한국어 `feat:` 커밋,
  `#352` 참조.
