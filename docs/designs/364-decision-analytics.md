# BE 설계: 판단 분석(analytics) API — 이슈 #364

상태: **계약 확정(Frozen)** — 2026-07-21. 상위 트래킹 BE #354(3차). 에픽 #347.
정본 상위 [[348-decision-log-redesign]]. 신규 마이그레이션 없음(기존 테이블 집계).

## 배경

판단 기록이 쌓이면 사용자의 투자 습관을 분석할 수 있다(스펙 §15). 반복 판단 패턴과 품질을
**순수 DB 집계**로 산출한다. AI 문장 생성은 이 단계 밖이며, 지표는 정량 로직으로만 만든다.
편향은 확정 진단하지 않고 정량 지표(예: 반대근거 작성률)로 대체 제시한다(§16).

## 1. API 계약

| Method · Path | 책임 | response |
| --- | --- | --- |
| `GET /api/v1/decision-logs/analytics` | 판단 패턴·품질 집계 | `DecisionAnalyticsResponse` |

Auth 필수, 소유권 `user_id`. 공통 엔벨로프. 리터럴 경로이므로 `/{decision_log_id}` 보다 먼저
등록.

## 2. 응답 스키마 `DecisionAnalyticsResponse`

체인 링크(판단→후속 판단)가 필요한 지표는 제외하고, 단일 판단·복기·근거·위험 집계로
산출 가능한 것만 담는다.

- `total_count`: int — 전체 판단 수.
- `decision_type_distribution`: `[{type, count, share}]` — 유형 분포.
- `counter_argument_rate`: float — 반대 근거(`relationship=CONTRADICTING` evidence)를 가진
  판단 비율. 충동/편향 정량 지표.
- `confidence_distribution`: `[{level, count, share}]` — 확신 수준 분포.
- `outcome_by_confidence`: `[{level, thesis_result, count}]` — 확신 수준별 복기 결과(고확신
  판단의 성과 파악).
- `risk_tag_frequency`: `[{type, count}]` — 위험 태그 빈도(내림차순).
- `review_adherence`: `{reviewed_count, overdue_count, adherence_rate}` — 재검토 준수율.
  overdue = 재검토 도래(REVIEW_DUE 또는 PENDING DATE 트리거 scheduled_at<=now)했으나 미복기.
- `process_quality_averages`: `{<항목>: avg}` — 복기 process_quality 항목별 평균(있는 항목만).
- `as_of`: UtcDatetime.

## 3. 집계 규칙 (요지)

- 전부 사용자 소유 레코드만.
- `counter_argument_rate` = CONTRADICTING evidence를 1개 이상 가진 판단 수 / 전체.
- `outcome_by_confidence` = `decision_logs`⋈`decision_reviews`를 confidence_level·thesis_result로
  group.
- `risk_tag_frequency` = `decision_risks`를 risk_type로 group.
- `review_adherence`: reviewed_count = 복기 있는 판단, overdue_count = 재검토 도래했으나 미복기.
- `process_quality_averages`: 복기 `process_quality` JSON의 수치 항목 평균(항목 합집합, 결측
  제외).
- total_count=0이면 비율 0·빈 목록으로 안전 반환.

## 4. Service / Repository (스켈레톤)

`DecisionLogRepository`(또는 신규 `analytics_repository`)
- `aggregate_analytics(user_id, now) -> AnalyticsAgg` — 위 지표를 집계.

`DecisionAnalyticsService`
- `get_analytics(user_id) -> DecisionAnalyticsResponse` — 집계 호출·응답 매핑.

## 5. 범위 밖(후속)

- 체인 링크 지표(추가 리서치 후 행동 비율 등) — 판단 간 연결 추적 필요, 후속.
- insight 문장 AI 생성(집계 후 별도), 거래 결과 연동(주문 도메인 부재), 투자 원칙 준수.
- 유사 판단 검색(#365).

ADR 불필요(읽기 집계, 계획된 3차 구현). Failure Record 불필요.
