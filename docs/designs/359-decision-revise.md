# BE 설계: 판단 버전 관리(revise) — 이슈 #359

상태: **계약 확정(Frozen)** — 2026-07-21. 상위 트래킹 BE #353(2차). 에픽 #347.
정본 상위 [[348-decision-log-redesign]] §3.1(`superseded_by_id`)·ADR-016 §5(버전 관리)를 따른다.
신규 마이그레이션 없음(`superseded_by_id`는 #349에서 생성됨).

## 배경

확정(ACTIVE 이후)된 판단을 조용히 수정하면 과거 판단을 미화하게 된다(ADR-016 §5). 원본을
보존한 채, 이전 판단을 대체하는 **새 DRAFT 판단**을 생성해 연결한다.

## 1. API 계약

| Method · Path | 책임 | request | response |
| --- | --- | --- | --- |
| `POST /api/v1/decision-logs/{id}/revise` | 원본을 대체하는 새 DRAFT 판단 생성 | 없음(또는 선택 override) | `DecisionLogDetailResponse` |

Auth 필수, 소유권. 없음 404 `DECISION_LOG_NOT_FOUND`, 타인 403 `DECISION_LOG_FORBIDDEN`.

## 2. 동작

- 원본 판단은 **변경하지 않는다**(본문·근거·상태 그대로), 단 `superseded_by_id`만 새 판단
  id로 세팅한다(원본이 새 판단으로 대체됨을 앞으로 가리킴).
- 새 판단: `status=DRAFT`, 원본의 `target`/`decision_type`/`thesis`/`rationale`/
  `confidence_level`를 복제. 원본의 `decision_evidence`·`decision_risks`·
  `decision_review_triggers`도 새 판단으로 복제한다(당시 근거를 이어받아 편집 가능하게).
  `decision_snapshots`는 복제하지 않는다(스냅샷은 확정 시점 값이므로 새 판단이 activate 시
  다시 캡처).
- 상태 제약: 원본이 `DRAFT`이면 revise 불가 → 409 `DECISION_LOG_INVALID_STATE`(초안은 그냥
  수정). `CANCELLED`도 불가. 이미 `superseded_by_id`가 있으면(이미 대체됨) 409.
- 반환: 새로 생성된 DRAFT 판단 상세.

## 3. Service / Repository (스켈레톤)

`DecisionLogRepository`
- `revise(source: DecisionLog) -> DecisionLog` — 원본 복제로 새 DRAFT 생성, 근거·위험·
  트리거 복제, 원본 `superseded_by_id` 세팅, 단일 트랜잭션.

`DecisionLogService`
- `revise(decision_log_id, user_id) -> DecisionLogDetailResponse` — 소유 확인 → 상태 가드 →
  `repo.revise` → 상세 반환.

## 4. 범위 밖(후속)

버전 이력·타임라인 FE 표시(#253), 대체 체인 조회 API. ADR 불필요(ADR-016 §5 계획된 구현).
