# Codex Handoff Task

## Source Issue

설계: `docs/designs/052-decision-log-stats.md` (Frozen)

## Task Summary

판단 통계 읽기 전용 엔드포인트 `GET /api/v1/decision-logs/stats`를 추가합니다. 응답은 사용자 전체 기간의
`decision_type`별 건수와 최근 검토된 판단 상위 N건을 포함합니다. 모델/마이그레이션 변경은 없습니다.

## Goal

- `GET /api/v1/decision-logs/stats`가 `ApiResponse[DecisionLogStatsResponse]`를 반환한다.
- `decision_type_counts`(전체 기간 유형별 건수)·`total`·`recent_reviewed`(최근 검토 상위 N건)를 진실되게 산출한다.
- 기존 목록/단건/생성/수정 엔드포인트 동작은 불변.

## Background — 오케스트레이터가 확정한 사실

- 설계 052가 정본이며 계약은 동결됨. 아래대로 구현할 것.
- 목록 API는 페이지네이션(size 기본 20)이라 FE 클라이언트 집계로는 전체 분포를 낼 수 없어 BE 집계가 필요함.
- `recent_reviewed`는 `reviewed_at IS NOT NULL`인 항목만, `reviewed_at` desc 정렬, `RECENT_REVIEWED_LIMIT=5` 적용.
- 회고 메모(`review_note`) 같은 신규 필드는 도입하지 않는다. `recent_reviewed`의 표시 텍스트는 기존
  `reason`/`risk_note` 필드를 그대로 노출(BE에서 합성·의미분류 금지).
- `decision_type_counts`는 존재하는 유형만 키로 포함(0건 유형 키 생략). `total`은 counts 합.

## Implementation Scope

- `app/domains/decision_logs/schema.py`
  - `DecisionLogStatsResponse`(필드: `decision_type_counts: dict[str, int]`, `total: int`,
    `recent_reviewed: list[ReviewedDecisionItem]`) 추가.
  - `ReviewedDecisionItem`(`id`, `ticker`, `company_name`, `decision_type`, `reason`, `risk_note`,
    `reviewed_at`) 추가. `reviewed_at`은 `UtcDatetime`.
- `app/domains/decision_logs/repository.py`
  - `count_by_decision_type(user_id) -> dict[str, int]`: `decision_type` GROUP BY count.
  - `list_recent_reviewed(user_id, limit) -> list[DecisionLog]`: `reviewed_at` not null 필터 +
    `reviewed_at` desc 정렬 + limit.
- `app/domains/decision_logs/service.py`
  - 모듈 상수 `RECENT_REVIEWED_LIMIT = 5`.
  - `get_stats(user_id) -> DecisionLogStatsResponse`: 위 두 리포지토리 메서드를 호출해 응답 구성.
    0건이면 빈 맵·빈 리스트·`total=0`.
- `app/api/v1/endpoints/decision_logs.py`
  - `GET /stats` 라우트 추가(`get_current_user` 의존, `success` 래퍼). `/{decision_log_id}` 라우트보다
    먼저 선언해 경로 충돌을 피한다.

## Out of Scope

- 모델/마이그레이션 변경, `review_note` 등 신규 컬럼.
- 상단 요약 카드용 별도 계약(본 응답의 `total`/counts로 후속 교정 예정, 이번엔 미적용).
- 의미 분류(섹터/테마) 하드코딩, 텍스트 합성.
- 기존 목록/단건/생성/수정 동작 변경.

## Protected Files

없음.

## Requirements

- 읽기 전용. 쓰기·외부 호출 없음.
- mypy strict 통과(테스트 함수 파라미터 포함 타입 주석 필수).
- `/stats`가 `/{decision_log_id}`로 잘못 매칭되지 않도록 라우트 순서 보장.

## Test Requirements

`tests/test_decision_logs.py`(또는 해당 파일)에 추가:
- 다유형 혼재 시 `decision_type_counts`가 유형별 정확한 건수, `total`이 합과 일치.
- 0건 사용자에서 빈 맵·빈 리스트·`total=0`.
- `recent_reviewed`가 reviewed(=`reviewed_at` not null)만 포함하고 `reviewed_at` desc 정렬·limit 준수.
- 타 사용자 데이터가 섞이지 않음(user 스코프).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q`

## Documentation Impact

- `docs/designs/052-decision-log-stats.md` 추가됨(정본).
- 이 핸드오프 문서 추가.

## ADR Need

불요. 기존 도메인에 읽기 전용 집계 엔드포인트 추가, 신규 아키텍처 결정 없음.

## Failure Record Need

불요. 국소 추가, 회귀는 테스트로 커버.

## Risk Level

Low. 읽기 전용 additive 엔드포인트, 기존 동작 불변.

## Expected Output

- 위 4개 파일 변경 + 테스트 추가.
- 브랜치 `feat/decision-log-stats`에 커밋(한국어 메시지).

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
