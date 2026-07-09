# Codex Handoff Task

## Source Issue

이슈 #243 — 관심종목 분석 파이프라인 트리거 연결: 추가 시 큐잉·세션 밴드 스케줄·수동 트리거 정비

설계 문서: `docs/designs/243-analysis-triggers.md`

## Task Summary

트리거 3종을 구현해 관심종목 추가부터 시그널·리포트 생성까지의 체인을 완성한다:
(1) 종목 추가 시 분석 잡 자동 큐잉, (2) 세션 밴드 기반 스케줄 등록,
(3) 수동 트리거에 인증·rate limit 추가.

## Goal

다음이 모두 참이면 완성이다:

- 관심종목에 종목을 추가하면 해당 watchlist의 분석 잡이 자동으로 큐에 적재된다.
  Redis 다운 등 큐잉 실패 시 종목 추가 자체는 성공으로 반환된다.
- `analyze_all_watchlists_job`이 레지스트리에 4개 세션 밴드 cron으로 등록된다.
  `ANALYSIS_SCHEDULE_ENABLED=false`(기본)일 때 등록은 되지만 `enabled=False`여서
  `cron_config.py`가 rq에 등록하지 않는다.
- `POST /api/v1/worker/jobs/analysis`가 미인증 요청에 401을 반환하고, 인증된 사용자가
  60초 내 2회 이상 호출하면 429를 반환한다.
- `uv run ruff check .`, `uv run mypy .`, `uv run pytest` 모두 통과한다.

## Background

분석 파이프라인(`WatchlistAnalysisService.run`)은 구현 완료 상태다. URL 기준 2중 중복 제거로
트리거가 고빈도 발동해도 새 뉴스가 없으면 LLM 호출이 발생하지 않는다
(`app/worker/jobs/analysis.py:12-38`).

스케줄러는 RQ 내장 cron을 사용하며 UTC 기준으로 해석한다. 기존 전례:
`price_collection` cron `10 22 * * 1-5` (`app/scheduler/registry.py:30`).
cron_config가 모듈 임포트 시 `_register_cron_jobs()`를 실행하므로 레지스트리 변경 즉시 적용된다
(`app/scheduler/cron_config.py:6-12`).

현재 `enqueue_analysis_job`은 인증이 없다. 같은 파일의 `enqueue_llm_analysis_job`은
`get_current_user`를 사용한다(`worker.py:88`). 이번 범위에서 `enqueue_analysis_job`만
정비하며 `enqueue_news_job`·`run_scheduler_job_once`는 변경하지 않는다.

## Implementation Scope

Codex가 변경할 수 있는 파일과 동작:

1. **`app/worker/jobs/analysis.py`**
   - `enqueue_watchlist_analysis_safe(watchlist_id: int) -> None` 추가 — 큐 적재 후 실패 억제·경고 로그
   - `analyze_all_watchlists_job() -> None` 추가 — DB에서 watchlist id 전수 조회 후 watchlist당 `WatchlistAnalysisService.run(watchlist_id)` 순차 실행, 단일 JobRun 추적, watchlist 단위 실패 격리

2. **`app/core/config.py`**
   - `Settings`에 `ANALYSIS_SCHEDULE_ENABLED: bool = False` 추가 (env `ANALYSIS_SCHEDULE_ENABLED`)

3. **`app/scheduler/registry.py`**
   - 아래 4개 `ScheduleDefinition` 추가 (모두 `enabled=settings.ANALYSIS_SCHEDULE_ENABLED`):

   | 등록 이름 | cron | KST 의미 |
   |----------|------|---------|
   | `analysis_kr_open` | `0 23 * * 0-4` | 평일 08:00 (요일 경계: UTC 일~목) |
   | `analysis_kr_main` | `0 0-7 * * 1-5` | 평일 09:00–16:00 |
   | `analysis_us_session` | `0 13-21 * * 1-5` | 평일 22:00–다음날 06:00 |
   | `analysis_kr_post` | `0 9,11 * * 1-5` | 평일 18:00, 20:00 |

   UTC 변환 검산은 `docs/designs/243-analysis-triggers.md`의 변환 표를 참고한다.

4. **`app/core/error_codes.py`**
   - `RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"` 추가

5. **`app/api/v1/endpoints/worker.py`**
   - `enqueue_analysis_job`에 `current_user: User = Depends(get_current_user)` 추가
   - rate limit 검사 추가: Redis 키 `rate_limit:analysis_manual:{user_id}` TTL 60초. 키 존재 시 HTTP 429 + `Retry-After: 60` 헤더 반환.
   - rate limit 키가 없을 때 SET NX+EX(60) 원자 연산으로 설정 후 enqueue 진행.

   **구현 전 확인:** `rate_limit:` 접두사 키 스킴이 기존 코드에 없음이 확인되지 않았다 (가정).
   `grep -r "rate_limit" app/`로 검색해 기존 패턴이 있으면 그 스킴을 따른다.

6. **`app/api/v1/endpoints/watchlists.py`**
   - `add_watchlist_item` 핸들러에서 `add_item` 반환 후 `enqueue_watchlist_analysis_safe(watchlist_id)` 호출. 응답 형태는 변경 없음.

7. **`docs/knowledge/product-workflow.md`**
   - "스케줄러" 섹션: `analysis_kr_open`·`analysis_kr_main`·`analysis_us_session`·`analysis_kr_post` 등록 사실과 `ANALYSIS_SCHEDULE_ENABLED` 플래그 추가
   - 다이어그램 `trigger` 블록에 `SCHED` 노드가 `analyze_all_watchlists_job`도 적재한다는 내용 반영
   - 관심종목 분석 파이프라인 섹션에 "종목 추가 시 자동 큐잉" 트리거 경로 추가

8. **테스트 파일** (아래 Test Requirements 참고)

## Out of Scope

Codex가 변경해서는 안 되는 것:

- FE 동기화 버튼 연동 (FE repo 별도)
- `enqueue_news_job`, `run_scheduler_job_once` 인증 추가
- 시장별 universe 분리, 주말 회차 스케줄
- cron 문자열 env 오버라이드
- 분석 파이프라인 내부 로직 (`WatchlistAnalysisService`)
- DB 스키마 변경 (migration 불필요)
- `app/scheduler/cron_config.py` 로직 변경 (`_register_cron_jobs` 루프는 그대로 사용)

## Protected Files

- `AGENTS.md`, `CLAUDE.md`, `.codex/` 하위 파일 — 변경 금지

## Requirements

수용 기준 (이슈 #243 요구사항을 검증 가능하게 번역):

1. **자동 큐잉**
   - `POST /api/v1/watchlists/{watchlist_id}/items` 성공 후 `analyze_watchlist_job`이
     Redis 큐에 적재된다.
   - Redis 연결 오류가 발생해도 응답은 HTTP 201이다.

2. **스케줄 등록**
   - `default_scheduler_registry.list()`에 `analysis_kr_open`, `analysis_kr_main`,
     `analysis_us_session`, `analysis_kr_post` 4개가 포함된다.
   - 각 항목의 cron이 변환 표와 일치한다.
   - `ANALYSIS_SCHEDULE_ENABLED=false`(기본)일 때 4개 항목 모두 `enabled=False`다.
   - `ANALYSIS_SCHEDULE_ENABLED=true`일 때 4개 항목 모두 `enabled=True`다.

3. **수동 트리거 정비**
   - 미인증 요청 → HTTP 401.
   - 인증된 사용자가 60초 내 2회 호출 시 두 번째 요청 → HTTP 429.
   - 정상 요청(첫 호출, 인증 완료) → HTTP 200, `{"job_id": ..., "status": "queued"}`.

4. **dev/demo 프로필 분리**
   - `Settings()` 기본 생성 시 `ANALYSIS_SCHEDULE_ENABLED == False`.
   - env `ANALYSIS_SCHEDULE_ENABLED=true` 주입 시 `True`.

## Test Requirements

다음 케이스를 신규 또는 갱신 테스트로 커버한다. 테스트 파일의 mock 방식은 기존 `test_scheduler.py`
의 `FakeQueue`·`FakeQueuedJob` 패턴과 `test_worker_jobs.py`의 `monkeypatch` 패턴을 따른다.

**`tests/test_scheduler.py`**

- `test_default_scheduler_registry_contains_only_collection_jobs` — 이름이 4개 분석 항목을
  포함하도록 갱신 (기존: collection 2개만 단언, 추가 후 실패함)
- `test_analysis_schedule_enabled_flag_controls_all_analysis_entries` — `ANALYSIS_SCHEDULE_ENABLED=True`
  주입 시 4개 분석 항목 모두 `enabled=True`, 기본값(False) 시 모두 `enabled=False`
- `test_cron_config_registers_enabled_scheduler_jobs` — `ANALYSIS_SCHEDULE_ENABLED=True` 환경에서
  분석 항목 4개가 rq에 등록되는지, `False`일 때 등록되지 않는지 검증

**`tests/test_worker_jobs.py`**

- `test_enqueue_analysis_job_api` — `set_current_user` 추가 (인증 추가로 기존 테스트 실패 예정)
- `test_enqueue_analysis_job_requires_auth` — 미인증 요청 시 HTTP 401
- `test_enqueue_analysis_job_rate_limit_allows_first_call` — 첫 요청 HTTP 200
- `test_enqueue_analysis_job_rate_limit_blocks_second_call` — Redis 키 존재 시 HTTP 429
  (Redis mock: `monkeypatch`로 `get_redis_connection`을 교체해 키 반환 조작)

**`tests/test_watchlists.py` 또는 신규 `tests/test_watchlist_analysis_autoqueue.py`**

- `test_add_watchlist_item_enqueues_analysis_job` — 종목 추가 후 큐 적재 확인
  (Queue mock: `monkeypatch`로 `enqueue_watchlist_analysis_safe`의 Queue를 대체)
- `test_add_watchlist_item_succeeds_even_if_enqueue_fails` — 큐잉 측에서 예외를 던져도
  HTTP 201 반환

**픽스처 주의:** 테스트에 들어가는 cron 문자열 리터럴은 설계 문서의 변환 표에서 복사하고
출처(`docs/designs/243-analysis-triggers.md` 변환 표)를 주석으로 남긴다.
`rate_limit:analysis_manual:{user_id}` 키 스킴이 가정임을 구현 전 확인한 뒤, 실제 값과
다르면 픽스처도 함께 수정한다.

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/243-analysis-triggers.md` — 이 핸드오프의 선행 설계 문서 (이미 작성됨)
- `docs/knowledge/product-workflow.md` — Implementation Scope 7번 항목 참고

## ADR Need

불필요. 기존 RQ cron 관례(`ADR-003`)의 확장이며 새로운 아키텍처 결정이 없다.
rate limit은 기존 Redis를 재사용해 새 인프라 도입 없음.

## Failure Record Need

불필요. 이번 구현은 기존 결함 수정이 아니라 신기능 추가다.

## Risk Level

Medium.

rate limit용 Redis 읽기가 `enqueue_analysis_job` 경로에 추가되므로 Redis 다운 시 수동 트리거가
영향받을 수 있다. 자동 큐잉 경로는 실패를 억제하므로 영향 없다. 스케줄 등록은 `cron_config.py`
임포트 시 실행되므로 `ANALYSIS_SCHEDULE_ENABLED` 기본값이 `False`인지 반드시 확인한다.

## Expected Output

- 변경된 파일: `app/worker/jobs/analysis.py`, `app/core/config.py`, `app/scheduler/registry.py`,
  `app/core/error_codes.py`, `app/api/v1/endpoints/worker.py`, `app/api/v1/endpoints/watchlists.py`,
  `docs/knowledge/product-workflow.md`
- 갱신/신규 테스트 파일: `tests/test_scheduler.py`, `tests/test_worker_jobs.py`,
  `tests/test_watchlists.py` 또는 `tests/test_watchlist_analysis_autoqueue.py`
- 세 가지 검증 명령 모두 통과

## Rules

- **현재 브랜치(`feat/243-analysis-triggers`) 유지 — 새 브랜치 생성 금지.**
- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- `rate_limit:` 키 스킴이 가정으로 표기되어 있으므로, 구현 전 `grep -r "rate_limit" app/`로
  기존 패턴 확인 후 일치시킨다. 기존 패턴 없으면 설계 문서의 스킴을 그대로 사용한다.
- 테스트 픽스처 내 cron 리터럴은 설계 문서에서 복사하고 출처 주석을 남긴다
  (`quality-process-policy.md` Real-Contract Fixtures 규율).
