# Codex Handoff Task

## Source Issue

BE #364 — 판단 분석(analytics) API. 상위 #354(3차). Epic #347.

## Task Summary

`GET /api/v1/decision-logs/analytics`를 구현한다. 순수 DB 집계로 반복 판단 패턴·품질 지표를
반환한다. 신규 마이그레이션 없음.

## Goal

- `GET /api/v1/decision-logs/analytics`가 `DecisionAnalyticsResponse`를 반환한다.
- 모든 지표가 사용자 소유 레코드만 대상으로 DB 집계된다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/364-decision-analytics.md`이며 반드시 먼저 읽고 따른다. 와이어·
엔벨로프·소유권은 기존 decision_logs와 동일. overview 집계(`aggregate_overview`)가 좋은
선례다.

지표(설계 §2·§3): `total_count`, `decision_type_distribution`, `counter_argument_rate`,
`confidence_distribution`, `outcome_by_confidence`, `risk_tag_frequency`, `review_adherence`,
`process_quality_averages`, `as_of`.

## Implementation Scope

- `app/domains/decision_logs/schema.py` — `DecisionAnalyticsResponse`(+ 중첩 항목 스키마).
- `app/domains/decision_logs/repository.py` — `aggregate_analytics(user_id, now)` 집계
  (func.count·group_by·조인). 행별 반복 쿼리 금지, 상수 쿼리 수.
- `app/domains/decision_logs/`(신규 `analytics_service.py` 또는 기존 service) —
  `get_analytics(user_id) -> DecisionAnalyticsResponse`.
- `app/api/v1/endpoints/decision_logs.py` — `GET /analytics` 라우트(리터럴 경로이므로
  `/{decision_log_id}` 보다 먼저 등록).
- 테스트.

## Out of Scope

- 체인 링크 지표(추가 리서치 후 행동 비율 등), insight AI 문장 생성, 거래 연동, 원칙 준수.
- 유사 판단 검색(#365), FE(#260).
- 스키마 변경(집계만).

## Protected Files

없음.

## Requirements

- 집계는 DB 쿼리로 산출(파이썬 루프 최소화). 사용자 소유만.
- `counter_argument_rate` = CONTRADICTING evidence 1개 이상 가진 판단 수 / 전체.
- `outcome_by_confidence` = decision_logs⋈decision_reviews를 confidence_level·thesis_result
  group.
- `risk_tag_frequency` = decision_risks를 risk_type group(내림차순).
- `review_adherence`: reviewed_count/overdue_count/adherence_rate. overdue = 재검토
  도래(REVIEW_DUE 또는 PENDING DATE 트리거 scheduled_at<=now)했으나 미복기.
- `process_quality_averages`: 복기 process_quality JSON 수치 항목 평균(결측 제외).
- total_count=0이면 비율 0·빈 목록으로 안전 반환(0 나눗셈 없음).

## Test Requirements

- 유형/확신 분포·share 합 ≈ 1.
- counter_argument_rate: CONTRADICTING 유무에 따른 비율.
- outcome_by_confidence: 확신×복기 결과 group 정확성.
- risk_tag_frequency 내림차순.
- review_adherence: 복기/미복기·도래 판단 계산.
- process_quality_averages: 항목별 평균(결측 제외).
- 0건 안전 반환, 타 사용자 격리.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

`docs/designs/364-decision-analytics.md` 정본, 이미 커밋. ADR·Failure Record 불필요.

## ADR Need

불필요.

## Failure Record Need

불필요.

## Risk Level

Low~Medium — 읽기 전용 집계, 조인·group 정확성이 핵심.

## Expected Output

- 변경 파일: schema/repository/service/endpoint + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/364-decision-analytics` 유지(새 브랜치 금지). 한국어 `feat:` 커밋, `#364`
  참조.
