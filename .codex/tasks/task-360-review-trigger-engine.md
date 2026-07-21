# Codex Handoff Task

## Source Issue

BE #360 — 이벤트 기반 재검토 트리거 감시. 상위 #353(2차). Epic #347.

## Task Summary

`PRICE`·`SIGNAL_CHANGE` 재검토 트리거를 주기적으로 평가해 조건 충족 시 판단을 `REVIEW_DUE`로
전이하는 엔진·워커를 추가한다. Alert 미연동, 상태 전이만. 신규 마이그레이션 없음.

## Goal

- `DecisionReviewTriggerService.run_cycle()`가 PENDING `PRICE`·`SIGNAL_CHANGE` 트리거(대상
  판단 `ACTIVE`)를 평가해 충족 시 트리거 `TRIGGERED`·판단 `REVIEW_DUE`로 전이한다.
- 워커 잡 `evaluate_decision_review_triggers_job`가 이 주기를 실행한다.
- `GET /decision-logs/review-queue`와 overview `review_due_count`가 `status == REVIEW_DUE`
  판단도 포함한다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/360-review-trigger-engine.md`이며 반드시 먼저 읽고 따른다. 선례는
`app/worker/jobs/alerts.py`(`evaluate_alert_rules_job` + `AlertEngineService.run_cycle()`).

condition 스키마(§1):
- `PRICE`: `{"op":"gte"|"lte","value":number}` vs 대상 `symbol` 현재가.
- `SIGNAL_CHANGE`: `{"to":"<SignalType>"}` — 대상 자산 현재 시그널 유형 == `to`.
- `METRIC`·`EVENT`: 스키마만, 평가 후속(이 태스크에서 평가 구현하지 않음, PENDING 유지).
- `DATE`: 엔진이 다루지 않음(review-queue 기존 로직 유지).

현재 데이터 소스(재사용): 현재가는 prices 도메인, 현재 시그널은
`app/domains/signals/service.py`의 `list_current_signals`(또는 repository의 current 조회).

## Implementation Scope

- `app/domains/decision_logs/`(신규 예: `review_trigger_service.py`) —
  `DecisionReviewTriggerService.run_cycle() -> 요약`. 유형별 조건 평가·전이.
- `app/domains/decision_logs/repository.py` — PENDING PRICE·SIGNAL_CHANGE 트리거(ACTIVE 판단)
  로드, 트리거 `TRIGGERED` 표시, 판단 `REVIEW_DUE` 전이.
- `app/worker/jobs/` — `evaluate_decision_review_triggers_job`(`alerts.py` 패턴, `JobRunService`
  기록).
- review-queue·overview 수정: `list_review_due`/`aggregate_overview`(#352/#351)가
  `status == REVIEW_DUE` 판단도 포함하도록 확장(판단 단위 중복 제거).
- 테스트.

## Out of Scope

- `METRIC`·`EVENT` 평가(스키마만), Alert 연동, 다회 재무장, 스케줄 자동 등록.
- FE.
- 신규 마이그레이션(스키마 이미 존재).

## Protected Files

없음.

## Requirements

- 전이는 판단이 `ACTIVE`일 때만 `REVIEW_DUE`로. 이미 `REVIEW_DUE`/이후 상태면 유지.
- 트리거 충족 시 `status=TRIGGERED`·`triggered_at=now`.
- 현재가·현재 시그널 부재, condition 파싱 실패는 해당 트리거 skip(1건 실패가 주기 비차단).
- review-queue·overview 확장은 기존 DATE 로직·소유권·페이지네이션을 유지하면서 REVIEW_DUE
  판단을 합집합으로 포함(중복 없이).
- 워커 잡은 기존 잡 등록 방식과 일관되게 배선.

## Test Requirements

- PRICE 트리거: 현재가가 조건 충족/미충족 시 전이 여부.
- SIGNAL_CHANGE 트리거: 현재 시그널이 `to`와 같을 때 전이.
- 전이 시 트리거 TRIGGERED·판단 REVIEW_DUE, 비-ACTIVE 판단은 전이 안 함.
- 데이터 부재·잘못된 condition skip(주기 비차단).
- review-queue·overview가 REVIEW_DUE 판단을 포함.
- 기존 DATE review-queue 동작 회귀 없음.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

`docs/designs/360-review-trigger-engine.md` 정본, 이미 커밋. ADR 불필요(상태 전이만, ADR-013
경계 불침범). Failure Record 불필요.

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Medium — 워커·크로스도메인 현재값 조회·상태 전이. Alert 미연동으로 결합은 낮음.

## Expected Output

- 변경 파일: review_trigger_service·repository·worker job·review-queue/overview 확장 + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/360-review-trigger-engine` 유지(새 브랜치 금지). 한국어 `feat:` 커밋,
  `#360` 참조.
