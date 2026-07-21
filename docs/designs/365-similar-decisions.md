# BE 설계: 유사 과거 판단 검색 — 이슈 #365

상태: **계약 확정(Frozen)** — 2026-07-21. 상위 트래킹 BE #354(3차). 에픽 #347.
정본 상위 [[348-decision-log-redesign]]. 신규 마이그레이션 없음.

## 배경

특정 판단과 유사한 과거 판단을 찾아 복기·의사결정에 참고한다(스펙 §25 3차). 임베딩 없이
**정량 유사도**(대상·유형·위험 태그 겹침)로 후보를 조회한다.

## 1. API 계약

| Method · Path | 책임 | response |
| --- | --- | --- |
| `GET /api/v1/decision-logs/{id}/similar?limit=` | 유사 과거 판단 목록 | `DecisionLogListItem[]` |

Auth 필수, 소유권(기준 판단이 본인 것). 없음 404 `DECISION_LOG_NOT_FOUND`, 타인 403
`DECISION_LOG_FORBIDDEN`. 응답 항목은 기존 경량 `DecisionLogListItem` 재사용.

## 2. 유사도 규칙 (요지)

기준 판단과 같은 사용자 소유의 다른 판단을 다음 신호로 점수화해 상위 N개 반환한다.

- 같은 대상(`symbol` 또는 `target_type`+`target_id`) 일치: 강한 신호.
- 같은 `decision_type` 일치: 중간 신호.
- 겹치는 `risk_type`(decision_risks) 수: 겹칠수록 가점.

점수 내림차순, 동점은 최신 `created_at`. 기준 판단 자신과 그 버전 체인
(`superseded_by_id`로 연결된 판단)은 제외한다. `limit` 기본 5, 상한 20.

## 3. Service / Repository (스켈레톤)

`DecisionLogRepository`
- `list_similar(base: DecisionLog, user_id, limit) -> list[DecisionLog]` — 위 신호로 후보
  조회·정렬(SQL 집계 + 파이썬 점수 보정 허용, 소규모).

`DecisionLogService`
- `list_similar(decision_log_id, user_id, limit) -> list[DecisionLogListItem]` — 소유 확인 후
  후보를 경량 항목으로 매핑(기존 `_to_list_items` 재사용, risks·review_at 배치 로딩).

## 4. 범위 밖(후속)

임베딩·텍스트 의미 유사도, 교차 사용자 벤치마크. ADR 불필요(읽기 조회, 계획된 3차 구현).
Failure Record 불필요.
