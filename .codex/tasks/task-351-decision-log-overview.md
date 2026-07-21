# Codex Handoff Task

## Source Issue

BE #351 — 판단 기록 요약(overview) API. Epic #347. ADR-016.

## Task Summary

판단 활동 현황을 압축한 `GET /api/v1/decision-logs/overview`를 구현하고, 기존
`GET /api/v1/decision-logs/stats`를 overview로 대체(삭제)한다.

## Goal

- `GET /api/v1/decision-logs/overview`가 설계 §4.3 `DecisionOverviewResponse`를 반환한다.
- 기존 `/stats` 엔드포인트·스키마·관련 테스트가 제거되고, overview 테스트로 대체된다.
- `uv run ruff check .` / `uv run mypy .` / `uv run pytest` 모두 통과.

## Background

정본 계약은 `docs/designs/348-decision-log-redesign.md` §4.3, ADR-016 §5. 소유권 `user_id`,
`get_current_user`, 공통 엔벨로프 `ApiResponse`/`success`, 시각 `UtcDatetime`.

`DecisionOverviewResponse` 필드와 산출 규칙:

- `total_count` — 사용자의 전체 판단 기록 수.
- `created_this_week` — 최근 7일 이내 생성분. 규칙: `created_at >= (now - 7 days)`.
  (설계의 "이번 주"를 롤링 7일로 확정한다 — 주 경계·타임존 모호성 회피. 결정 사유를 코드
  주석 한 줄로 남긴다.)
- `review_due_count` — 재검토가 도래한 판단 수. 규칙: `DATE` 재검토 트리거 중
  `status=PENDING` 이고 `scheduled_at <= now` 인 트리거를 가진 **판단(중복 제거)** 수.
- `active_count` — 진행 중 판단 수. 규칙: `status == ACTIVE`(향후 `REVIEW_DUE` 도입 시
  포함). 매수/매도 실행이 아니라 아직 결과 미평가·재검토 조건이 남은 판단을 뜻한다.
- `decision_type_distribution` — `[{type, count, share}]`. `share = count / total_count`
  (total_count=0이면 빈 목록 또는 share=0). `type`은 enum 값(영문). 정렬은 count 내림차순
  권장(동률은 type 알파벳).
- `as_of` — 응답 생성 시각(`UtcDatetime`).

## Implementation Scope

- `app/domains/decision_logs/schema.py` — `DecisionOverviewResponse`(+ 분포 항목 스키마)
  추가. 기존 `DecisionLogStatsResponse`·`ReviewedDecisionItem` 제거.
- `app/domains/decision_logs/repository.py` — overview 집계 메서드(총계·주간·review_due·
  active·유형분포). 기존 stats 전용 메서드(`list_recent_reviewed` 등) 중 미사용분 정리.
- `app/domains/decision_logs/service.py` — `get_overview(user_id) -> DecisionOverviewResponse`.
  기존 `get_stats` 제거.
- `app/api/v1/endpoints/decision_logs.py` — `GET /overview` 라우트 추가, `GET /stats` 제거.
  주의: `/overview`·`/stats` 같은 리터럴 경로는 `/{decision_log_id}` 보다 먼저 등록해
  경로 충돌을 피한다(기존 stats가 그랬듯).
- `tests/test_decision_logs.py`(+ 필요 시 `tests/test_api_contract.py`) — overview 테스트
  추가, stats 테스트 제거.

## Out of Scope

- 목록 필터 확장·review-queue(#352), 복기·버전(2차).
- 집계 문장의 AI 생성(3차). overview 숫자는 순수 DB 집계여야 한다.
- 다른 도메인, FE.

## Protected Files

없음.

## Requirements

- 모든 카운트는 사용자 소유 레코드만 집계한다.
- 집계는 DB 쿼리로 산출한다(파이썬 루프 최소화). 가능하면 `func.count`·`group_by` 사용.
- `review_due_count`는 판단 단위 중복 제거(한 판단에 due 트리거가 여러 개여도 1로 셈).
- 빈 상태(0건)에서 예외 없이 0·빈 분포를 반환.

## Test Requirements

- 0건일 때 total/카운트/분포가 0·빈 목록.
- 유형이 여러 개일 때 분포 count·share 정확성(share 합 ≈ 1).
- `created_this_week` 경계: 7일 이전 생성분 제외, 이내 포함.
- `review_due_count`: due한 DATE 트리거(PENDING, scheduled_at<=now)를 가진 판단만, 판단
  단위로 셈.
- 타 사용자 레코드가 섞여도 본인 것만 집계.
- `/stats` 제거 후 해당 경로가 사라졌는지(404 또는 라우트 없음).

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

설계문서·ADR 정본. `/stats` 제거는 설계 §4가 이미 명시했다. 추가 문서 변경 불필요.

## ADR Need

불필요(ADR-016 구현).

## Failure Record Need

불필요.

## Risk Level

Low — 읽기 전용 집계. 스키마·CRUD는 #349/#350에서 확정됨.

## Expected Output

- 변경 파일: schema/repository/service/endpoint + 테스트.
- 검증 3종 통과 로그.
- 현재 브랜치 `feat/348-decision-log-redesign` 유지(새 브랜치 금지). 한국어 `feat:` 커밋,
  `#351` 참조.
