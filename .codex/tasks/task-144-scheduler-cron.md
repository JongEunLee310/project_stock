# Codex Handoff Task

## Source Issue

- BE #208 — 스케줄러 실 주기 연결 — RQ 내장 cron 등록·수집 잡 주기 실행
- milestone: 데이터 수집 파이프라인
- 설계: `docs/designs/079-scheduler-cron-and-llm-call-guard.md` Part A (§2·§3.1–3.6·§5 Part A)

## Task Summary

`app/scheduler/`의 inline 실행 구조를 RQ enqueue 기반으로 전환하고, RQ 내장 cron 설정 모듈을
신설해 수집 잡 2건을 주기 실행에 연결한다. `ManualSchedulerRunner`는 enqueue 전담으로
재작성하고 수동 실행 endpoint 응답 스키마를 RQ job id 기반으로 변경한다. `mock_collection`
잡과 `run_mock_collection_job` 함수는 삭제한다.

## Goal

- `app/scheduler/cron_config.py`가 신설되어 `uv run rq cron app/scheduler/cron_config.py -u $REDIS_URL`로
  스케줄러 프로세스를 기동할 수 있다.
- `default_scheduler_registry`에 `price_collection`(collect_prices_job, `"10 22 * * 1-5"`)·
  `news_collection`(collect_news_job, `"0 * * * *"`) 두 잡이 등록된다.
- `ManualSchedulerRunner.run(job_name)`은 RQ enqueue만 수행하며 자체 `JobRun` 기록을
  남기지 않는다.
- 수동 실행 endpoint가 `SchedulerJobRunResponse(job_name, job_id: str, status="queued")`를
  반환한다.
- 화이트리스트 회귀 단언: `default_scheduler_registry` 등록 함수 집합이
  `{collect_prices_job, collect_news_job}`에 포함됨을 단언한다.
- 검증 4종(ruff·mypy·pytest·alembic heads)이 전부 통과한다.

## Background

- ADR-003(`docs/decisions/ADR-003-scheduler-approach.md`)이 RQ 계열 주기 스케줄링을
  확정했다. 설계 044가 스켈레톤 구현을 남겼으나 실 cron 연결은 미완성이다.
- 현재 `app/scheduler/runner.py`의 `ManualSchedulerRunner`는 API 프로세스 안에서 잡을
  inline 실행하며 `JobRun`을 자체 기록한다. 수집 잡(`collect_prices_job`·`collect_news_job`)은
  실행 시간이 수 분에 달하므로 inline 실행은 부적합하다.
- RQ 2.9.1 내장 cron 등록: `rq.cron.register(func, queue_name, cron=...)`. CLI:
  `uv run rq cron <설정모듈경로> -u <redis url>`. 별도 패키지 불필요.
- 수집 잡은 자체적으로 `JobRun`을 `start→succeed/fail`로 기록한다
  (`app/worker/jobs/prices.py`·`app/worker/jobs/news.py` 참조). 스케줄러가 추가로
  `JobRun`을 기록하면 이중 기록이 발생한다.
- 지침 §15: 주기 잡에 LLM 호출 잡을 혼입해서는 안 된다.
- Decision EEE: RQ 내장 cron 채택, `cron_config.py` 신설.
- Decision FFF: 실행 경로 enqueue 일원화, `ManualSchedulerRunner` 재작성, 응답 스키마 변경.
- Decision GGG: 수집 잡 cron 표현식 확정, `mock_collection` 제거.

## Implementation Scope

1. `app/scheduler/interface.py` — `FunctionSchedulerJob`에서 inline `run` 메서드 개념 제거.
   `ScheduleDefinition`이 worker 잡 함수 참조를 직접 유지하는 프로토콜로 정리.
2. `app/scheduler/registry.py` — `mock_collection` 제거. `price_collection`(collect_prices_job,
   `"10 22 * * 1-5"`)·`news_collection`(collect_news_job, `"0 * * * *"`) 등록.
3. `app/scheduler/cron_config.py` (신규) — 모듈 임포트 시 `default_scheduler_registry`
   순회, `enabled=True`인 항목에 대해 `rq.cron.register(func, "default", cron=...)` 호출.
4. `app/scheduler/runner.py` — `ManualSchedulerRunner`를 enqueue 전담으로 재작성. RQ 큐에
   잡을 적재하고 RQ job id를 반환. 자체 `JobRun` 기록 제거.
5. `app/api/v1/endpoints/worker.py` — `run_scheduler_job_once`: `SchedulerJobRunResponse`의
   `job_run_id` 필드를 `job_id: str`로 교체, `status="queued"` 반환. 404·409 오류 계약
   유지.
6. `app/scheduler/jobs.py` — `run_mock_collection_job` 함수 삭제.
7. 테스트:
   - `rq.cron.register`를 fake로 잡아 `cron_config` 임포트 시 등록 목록과 cron 표현식을 단언.
   - `ManualSchedulerRunner.run(job_name)` 호출 시 `rq.Queue.enqueue`가 해당 잡 함수로
     호출되는지 단언. `AsyncMock` 사용 금지(sync 코드베이스).
   - 화이트리스트 회귀: `default_scheduler_registry` 등록 함수 집합이
     `{collect_prices_job, collect_news_job}`에 포함됨을 단언.
   - 기존 스케줄러 관련 테스트 갱신.
8. `docs/knowledge/product-workflow.md` — 스케줄러 섹션에 cron 기동 명령 추가.
9. `docs/backend-v0.2.md` — 스케줄러 프로세스 실행 명령·REDIS_URL 환경 변수
   기술 추가.
10. `docs/decisions/ADR-003-scheduler-approach.md` — Follow-up에 "RQ 내장 cron으로
    구체화됨" 항목 추가.

## Out of Scope

- `app/worker/jobs/prices.py`·`app/worker/jobs/news.py` 수집 잡 본체 변경.
- `app/adapters/llm/` 하위 파일 변경.
- 기존 alembic versions 변경.
- DB 스키마 변경·migration 생성.
- 다른 도메인 서비스 변경.

## Protected Files

- `app/worker/jobs/prices.py` — 변경 금지.
- `app/worker/jobs/news.py` — 변경 금지.
- `app/worker/jobs/analysis.py` — 변경 금지.
- `app/adapters/llm/` — 변경 금지.
- `alembic/versions/` — 변경 금지.
- `app/domains/` — 변경 금지.

## Requirements

- `cron_config.py` 임포트만으로 RQ cron 등록이 완료되어야 한다.
- `ManualSchedulerRunner`가 `JobRun`을 자체 기록하지 않는다.
- 수동 실행 endpoint가 `job_id(str)`·`status="queued"`를 반환한다.
- 타입 힌트 완전성(mypy 통과 수준).
- 주석은 WHY가 명확하지 않을 때만 최소한으로.

## Test Requirements

- cron 등록 목록 단언(cron_config 임포트 시 등록 잡·cron 표현식 일치).
- enqueue 경로 단언(ManualSchedulerRunner.run 호출 시 rq.Queue.enqueue 호출).
- 화이트리스트 회귀 단언(registry 함수 집합이 {collect_prices_job, collect_news_job} 포함).
- 기존 스케줄러 테스트 전부 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

`docs/knowledge/product-workflow.md`·`docs/backend-v0.2.md`·`docs/decisions/ADR-003-scheduler-approach.md`(Follow-up 갱신). 설계 `docs/designs/079-scheduler-cron-and-llm-call-guard.md`는 이 PR에 동봉된다.

## ADR Need

없음 — 설계 079 §6 참조. ADR-003 Follow-up 갱신으로 충분하다.

## Failure Record Need

없음 — 계획된 실 경로 연결이며 결함 마감이 아니다.

## Risk Level

중간. `ManualSchedulerRunner` 재작성과 응답 스키마 변경이 수반된다. 단, 수집 잡 본체와
LLM 어댑터는 변경되지 않으며, 내부 ops endpoint라 하위 호환 부담은 낮다.

## Expected Output

- 신규: `app/scheduler/cron_config.py`, 신규 테스트 파일.
- 수정: `app/scheduler/interface.py`, `app/scheduler/registry.py`, `app/scheduler/runner.py`,
  `app/scheduler/jobs.py`, `app/api/v1/endpoints/worker.py`, 영향받는 기존 테스트 파일,
  `docs/knowledge/product-workflow.md`, `docs/backend-v0.2.md`,
  `docs/decisions/ADR-003-scheduler-approach.md`.
- 검증 4종 통과.

## Decisions 요약 (설계 079 참조)

- EEE: RQ 내장 cron 채택, `cron_config.py` 신설(rq-scheduler·APScheduler 기각).
- FFF: 실행 경로 enqueue 일원화, `ManualSchedulerRunner` 재작성, 응답 스키마 `job_id/status="queued"` 변경.
- GGG: `price_collection` `"10 22 * * 1-5"`, `news_collection` `"0 * * * *"`, `mock_collection` 제거.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 브랜치(`feature/scheduler-cron-llm-call-guard`)를 유지한다. 커밋하지 않는다.
