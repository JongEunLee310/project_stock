# Codex Handoff Task

## Source Issue

PR #244 로컬 리뷰 후속 (이슈 #243, 리뷰 기록 `docs/reviews/pr-244.md`의 Q1·S1·S2).
개발자가 Q1에 대해 "watchlist ID 조회 실패 시에도 잡 실패 디버그가 가능하도록 JobRun을 기록"하기로 답변했다 (PR #244 코멘트).

## Task Summary

PR #244 리뷰의 확인 질문 1건과 비차단 제안 2건을 반영한다. 기능 추가 없음, 기존 구현 보완만.

## Implementation Scope

1. **Q1 — `analyze_all_watchlists_job`의 JobRun 기록 시점** (`app/worker/jobs/analysis.py`)
   - 현재: `select(Watchlist.id)` 조회가 `job_run_service.start()`보다 먼저 실행되어, 조회 실패 시 JobRun이 아예 기록되지 않는다.
   - 수정: watchlist ID 조회가 실패해도 JobRun이 `failed` 상태로 남도록 순서를 조정한다. `JobRunService.start(job_type, metadata)`를 먼저 호출하고(조회 전이므로 metadata의 `watchlist_ids`는 제외하거나 빈 값으로 시작), 이후 조회 결과를 확보한다. 조회 실패 시 기존 `except` 경로에서 `fail(job_run_id, ...)`이 호출되게 한다. metadata에 ID 목록을 남기는 기존 의도를 합리적인 방식으로 유지하되(예: 조회 성공 후 로그로 남기거나 metadata 반영 가능하면 반영), JobRun 모델·서비스 시그니처는 변경하지 않는다.
   - 테스트: watchlist ID 조회에서 예외가 발생해도 JobRun이 `failed`로 기록되는 케이스를 `tests/`의 기존 worker 잡 테스트 패턴(monkeypatch)으로 추가한다.

2. **S1 — rate limit 키 픽스처 출처 주석** (`tests/test_worker_jobs.py:323` 부근)
   - `rate_limit:analysis_manual:42` 리터럴에 출처 주석을 추가한다: `docs/designs/243-analysis-triggers.md`의 rate_limit Redis 키 스킴 (`rate_limit:analysis_manual:{user_id}`). quality-process-policy의 Real-Contract Fixtures 규율.

3. **S2 — 재시작 필요 명시** (`docs/knowledge/product-workflow.md`)
   - `ANALYSIS_SCHEDULE_ENABLED`가 `app/scheduler/registry.py` 모듈 임포트 시점에 평가되므로, env 변경 후 스케줄러 프로세스 재시작이 필요하다는 문장을 스케줄러 섹션에 추가한다.

## Out of Scope

- 분석 파이프라인·트리거 로직의 기능 변경
- JobRun 모델·서비스 시그니처 변경
- 기타 파일

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Rules

- **현재 브랜치(`feat/243-analysis-triggers`) 유지 — 새 브랜치 생성 금지. 커밋·push 금지 (오케스트레이터가 수행).**
- 위 3개 항목 외 변경 금지. drive-by 리팩터링 금지.
- 검증 3종 통과 후 변경 파일·결과를 보고한다.
