# BE 설계: 판단 복기(review) API — 이슈 #358

상태: **계약 확정(Frozen)** — 2026-07-21. 상위 트래킹 BE #353(2차). 에픽 #347.
정본 상위 문서 [[348-decision-log-redesign]] §3.6(테이블)·§2(enum)를 따른다. `decision_reviews`
테이블은 #349에서 이미 생성됐으므로 **신규 마이그레이션은 없다**.

## 배경

판단 복기는 일정 시간이 지난 뒤 판단을 평가하는 기능이다. **투자 결과와 판단 품질을 분리**해
저장한다(ADR-016 §6). 한 판단은 시간에 걸쳐 여러 번 복기될 수 있다.

## 1. API 계약

| Method · Path | 책임 | request | response |
| --- | --- | --- | --- |
| `POST /api/v1/decision-logs/{id}/reviews` | 복기 작성 | `DecisionReviewCreate` | `DecisionReviewResponse` |
| `GET /api/v1/decision-logs/{id}/reviews` | 복기 목록(최신순) | — | `DecisionReviewResponse[]` |

전부 Auth 필수, 소유권 `user_id`(대상 판단 소유자). 없음 404 `DECISION_LOG_NOT_FOUND`,
타인 403 `DECISION_LOG_FORBIDDEN`. 공통 엔벨로프.

리터럴 경로 `{id}/reviews`는 기존 `{decision_log_id}` 라우트와 method·subpath가 구분되므로
충돌 없음(등록 순서 주의).

## 2. 요청 스키마 `DecisionReviewCreate`

- `outcome_status`: `OutcomeStatus`(필수) — `THESIS_CONFIRMED | THESIS_PARTIALLY_CONFIRMED |
  THESIS_INVALIDATED | INSUFFICIENT_TIME | CLOSED`.
- `thesis_result`: `ThesisResult`(필수) — `CONFIRMED | PARTIALLY_CONFIRMED | INVALIDATED`.
- `process_quality`: `dict | None` — 판단 품질 항목별 점수(예: `evidence_quality`,
  `counter_argument_review`, `risk_awareness`, `review_condition_clarity`, `discipline`).
  자유 JSON(고정 스키마 강제하지 않음, 상위 §3.6 방침).
- `result_metrics`: `dict | None` — 투자 결과(예: `return_rate`, `benchmark_return_rate`,
  `max_drawdown`). 자유 JSON.
- `what_went_well` / `what_was_missed` / `what_to_change`: `str | None`.

**품질과 결과는 별도 필드**로 받는다. 하나로 합치지 않는다.

## 3. 응답 스키마 `DecisionReviewResponse`

`id`, `decision_id`, `outcome_status`, `thesis_result`, `process_quality`, `result_metrics`,
`what_went_well`, `what_was_missed`, `what_to_change`, `reviewed_at`(UtcDatetime),
`created_at`/`updated_at`.

## 4. 라이프사이클

복기 작성 시:
- `decision_reviews`에 레코드 생성, `reviewed_at`=서버 now(제공 시 그 값).
- 대상 판단 상태를 `REVIEWED`로 전이하고 `decision_logs.reviewed_at`이 null이면 스탬프.
  이미 `REVIEWED`면 유지(추가 복기 허용).
- `DRAFT` 판단에는 복기를 만들 수 없다 → 409 `DECISION_LOG_INVALID_STATE`
  (확정 전 판단은 복기 대상이 아님).

## 5. Service / Repository (스켈레톤)

`DecisionReviewRepository`
- `create(decision_id, DecisionReviewCreate, reviewed_at) -> DecisionReview` — 복기 생성.
- `list_by_decision(decision_id) -> list[DecisionReview]` — 최신순 목록.

`DecisionReviewService`(또는 기존 `DecisionLogService` 확장)
- `create_review(decision_id, user_id, DecisionReviewCreate) -> DecisionReviewResponse` —
  소유 판단 확인 → DRAFT 가드 → 복기 생성 → 판단 상태 REVIEWED 전이.
- `list_reviews(decision_id, user_id) -> list[DecisionReviewResponse]` — 소유 확인 후 목록.

## 6. 범위 밖(후속)

버전 관리 revise(#359), 이벤트 트리거·Alert(#360), 자동 근거 연결(#361), 당시/현재 비교·
타임라인 FE(#253). 품질 점수 자동 산정은 3차. ADR 불필요 — 상위 ADR-016의 계획된 구현이다.
