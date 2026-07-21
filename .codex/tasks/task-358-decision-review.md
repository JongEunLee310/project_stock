# Codex Handoff Task

## Source Issue

BE #358 — 판단 복기(review) API. 상위 #353(2차). Epic #347.

## Task Summary

판단 복기 API(`POST`/`GET /api/v1/decision-logs/{id}/reviews`)를 구현한다. `decision_reviews`
테이블은 #349에서 이미 생성됐으므로 신규 마이그레이션은 없다. 투자 결과와 판단 품질을
분리해 저장한다.

## Goal

- `POST /api/v1/decision-logs/{id}/reviews`가 복기를 생성하고 대상 판단을 `REVIEWED`로
  전이한다.
- `GET /api/v1/decision-logs/{id}/reviews`가 복기 목록(최신순)을 반환한다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/358-decision-review.md`이며 반드시 먼저 읽고 따른다. 상위
`docs/designs/348-decision-log-redesign.md` §3.6(테이블)·§2(enum: `OutcomeStatus`·
`ThesisResult`)도 참조. 와이어 컨벤션·엔벨로프·소유권은 기존 decision_logs와 동일.

핵심:
- `process_quality`와 `result_metrics`는 **별도 필드**(자유 JSON). 합치지 않는다.
- 복기 작성 시 판단 상태 `ACTIVE`/`REVIEW_DUE` → `REVIEWED`, `decision_logs.reviewed_at`
  null이면 스탬프. 이미 `REVIEWED`면 유지(추가 복기 허용).
- `DRAFT` 판단에 복기 생성은 409 `DECISION_LOG_INVALID_STATE`.

## Implementation Scope

- `app/domains/decision_logs/schema.py` — `DecisionReviewCreate`, `DecisionReviewResponse`
  (설계 §2·§3 필드).
- `app/domains/decision_logs/repository.py` — 복기 생성·목록(`decision_reviews` 사용). 기존
  `DecisionReview` 모델 재사용.
- `app/domains/decision_logs/service.py`(또는 신규 `review_service.py`) —
  `create_review`, `list_reviews`(소유 확인·DRAFT 가드·상태 전이).
- `app/api/v1/endpoints/decision_logs.py` — `POST`/`GET /{decision_log_id}/reviews` 라우트.
- 테스트.

## Out of Scope

- revise(#359), 이벤트 트리거·Alert(#360), 자동 근거 연결(#361), FE(#252).
- 품질 점수 자동 산정. `decision_reviews` 스키마 변경(이미 확정).

## Protected Files

없음.

## Requirements

- 소유권: 대상 판단이 호출자 소유여야 함. 없음 404, 타인 403.
- `outcome_status`·`thesis_result`는 enum 검증(422). `process_quality`/`result_metrics`는
  자유 JSON.
- 한 판단에 복수 복기 허용, 목록은 최신순(reviewed_at desc).

## Test Requirements

- 복기 생성 → 판단 상태 REVIEWED 전이·reviewed_at 스탬프.
- DRAFT 판단 복기 시 409.
- 품질·결과가 분리 저장·조회되는지.
- 복수 복기·최신순 목록.
- 소유권(타인 403)·잘못된 enum 422.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

`docs/designs/358-decision-review.md` 정본, 이미 커밋. ADR·Failure Record 불필요(ADR-016
계획된 구현).

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low~Medium — 신규 마이그레이션 없음, 상태 전이·분리 저장이 핵심.

## Expected Output

- 변경 파일: schema/repository/service/endpoint + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/358-decision-review` 유지(새 브랜치 금지). 한국어 `feat:` 커밋, `#358`
  참조.
