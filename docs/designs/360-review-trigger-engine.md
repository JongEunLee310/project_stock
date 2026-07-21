# BE 설계: 이벤트 기반 재검토 트리거 감시 — 이슈 #360

상태: **계약 확정(Frozen)** — 2026-07-21. 상위 트래킹 BE #353(2차). 에픽 #347.
정본 상위 [[348-decision-log-redesign]] §3.4(`decision_review_triggers`)·ADR-016.
신규 마이그레이션 없음.

## 결정 요지 (사용자 확정 2026-07-21)

트리거 조건이 충족되면 **판단 상태를 `REVIEW_DUE`로 전이**한다. Alert 도메인과 연동하지
않는다(별도 알림 미발생). 따라서 **ADR 불필요** — 판단 도메인 내부 상태 전이이며 ADR-013
경계를 넘지 않는다.

## 배경

`decision_review_triggers`는 재검토 조건을 저장한다(트리거 유형·`condition` JSON·
`scheduled_at`·`status`). 1차·복기까지는 `DATE` 트리거만 review-queue에서 조회 시점에
계산했다. 이 설계는 **이벤트 트리거(`PRICE`·`SIGNAL_CHANGE`)를 주기적으로 평가**해 조건
충족 시 판단을 `REVIEW_DUE`로 전이하는 워커·엔진을 추가한다. `METRIC`·`EVENT`는 조건
스키마만 정의하고 평가는 후속으로 미룬다.

기존 선례를 따른다: `AlertEngineService.run_cycle()` + `evaluate_alert_rules_job`
(`app/worker/jobs/alerts.py`).

## 1. 조건(condition JSON) 스키마

- `PRICE`: `{"op": "gte" | "lte", "value": <number>}` — 대상 `symbol`의 현재가와 비교.
- `SIGNAL_CHANGE`: `{"to": "<SignalType>"}` — 대상 자산의 현재 시그널 유형이 `to`와 같으면
  충족(해당 상태로 변경됨).
- `DATE`: `{}` — `scheduled_at` 컬럼 사용(엔진은 이 유형을 다루지 않음, review-queue 유지).
- `METRIC`: `{"metric": "<key>", "op": "gte"|"lte", "value": <number>}` — **스키마만 정의,
  평가 후속**.
- `EVENT`: `{"event_type": "<key>"}` — **스키마만 정의, 평가 후속**.

## 2. 엔진·워커

`DecisionReviewTriggerService`(신규, `app/domains/decision_logs/` 또는
`decision_review_engine`)
- `run_cycle() -> ReviewTriggerCycleSummary` — 평가 1주기. 책임:
  1. `status=PENDING`이고 대상 판단이 `ACTIVE`인 `PRICE`·`SIGNAL_CHANGE` 트리거를 로드.
  2. 유형별로 현재 데이터와 `condition` 비교(§1). 현재가는 prices 도메인, 현재 시그널은
     `SignalService.list_current_signals`(또는 repository) 재사용.
  3. 충족 시: 트리거 `status=TRIGGERED`·`triggered_at=now`, 대상 판단 `status`가 `ACTIVE`면
     `REVIEW_DUE`로 전이(이미 `REVIEW_DUE`/그 이후면 유지).
  4. 요약(평가 수·전이 수) 반환.
- 데이터 없음(현재가·시그널 부재)·파싱 실패는 해당 트리거를 건너뛴다(시스템 경계에서 안전
  처리, 1건 실패가 주기를 막지 않음).

워커 잡 `evaluate_decision_review_triggers_job`(`app/worker/jobs/`) — `alerts.py` 패턴 복제,
`JobRunService`로 실행 기록.

## 3. review-queue 반영

`GET /decision-logs/review-queue`(#352)를 확장한다. 기존 "PENDING `DATE` 트리거
`scheduled_at <= now`" 조건에 더해 **`status == REVIEW_DUE` 판단**도 포함한다(이벤트 트리거로
전이된 판단이 큐에 노출되도록). overview의 `review_due_count`도 동일 기준으로 맞춘다(중복
없이 판단 단위).

## 4. Repository (스켈레톤)

`DecisionReviewTriggerRepository`(또는 기존 repository 확장)
- `list_pending_event_triggers() -> list[(DecisionLog, DecisionReviewTrigger)]` — ACTIVE 판단의
  PENDING PRICE·SIGNAL_CHANGE 트리거.
- `mark_triggered(trigger, at)` / 판단 `REVIEW_DUE` 전이.

## 5. 범위 밖(후속)

- `METRIC`·`EVENT` 트리거 평가(스키마만 정의).
- Alert 연동(사용자 확정으로 미연동).
- 트리거 재무장(다회 발동)·스케줄 등록 자동화.
- FE 표시(#253/#255에서 REVIEW_DUE·재검토 큐 소비).

ADR 불필요(상태 전이만, ADR-013 경계 불침범). Failure Record 불필요.
