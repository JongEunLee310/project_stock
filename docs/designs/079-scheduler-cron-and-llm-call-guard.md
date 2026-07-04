# 079 · 스케줄러 cron 연결 및 LLM 호출 가드

Status: Draft
작성: Claude Code (orchestrator)
관련: BE #208(스케줄러 cron 연결), BE #209(LLM 호출 가드), Epic BE #141
지침 근거: `docs/knowledge/llm-data-pipeline.md` §15(LLM 호출 트리거 제한), §16(Redis rate limit 관리), ADR-003(스케줄러 방식 확정).

---

## 1. 배경

스케줄러와 LLM 호출 경계에 두 가지 미완성 요소가 남아 있다.

첫째, `app/scheduler/registry.py`는 `mock_collection` 잡을 `ManualSchedulerRunner`(API
프로세스 inline 실행)로만 구동하며, RQ cron 주기 실행에 연결되어 있지 않다. 실 수집 잡
(`collect_prices_job`·`collect_news_job`)은 실행 시간이 수 분에 달하므로 API 프로세스
inline 실행은 부적합하고, ADR-003이 확정한 RQ 계열 주기 스케줄링 방향과도 어긋난다.
RQ 2.9.1은 별도 패키지 없이 내장 cron을 제공하므로, 설계 044가 남긴 스켈레톤을 실 경로로
완성할 수 있다.

둘째, #206 수렴 이후 모든 LLM 호출이 `LLMGateway.complete_json`으로 집중되었지만, cloud
provider 호출에 대한 일일 상한 제어 장치가 없다. 지침 §15는 초기 단계에서 LLM 호출
트리거를 "사용자 직접 분석 요청·수동 ContextBundle 생성"으로만 허용하며, 주기 잡이 자동으로
LLM을 호출하는 경로는 이후 단계로 미뤄두고 있다. §16은 Redis 도입 시점에 API rate limit
관리를 명시한다.

두 작업은 독립적이나 같은 브랜치에서 순차 구현(Part A → Part B)한다.

## 2. 범위

### Part A — 스케줄러 cron 연결 (BE #208, Decision EEE·FFF·GGG)

포함:

- `app/scheduler/cron_config.py` — RQ 내장 cron 등록 모듈 신설.
- `app/scheduler/interface.py` — `FunctionSchedulerJob` 정리(inline run 개념 제거).
- `app/scheduler/registry.py` — 실 수집 잡 2건 등록, `mock_collection` 제거.
- `app/scheduler/runner.py` — `ManualSchedulerRunner`를 enqueue 전담으로 재작성, 자체 `JobRun`
  기록 제거.
- `app/scheduler/jobs.py` — `run_mock_collection_job` 삭제.
- `app/api/v1/endpoints/worker.py` — 수동 실행 endpoint 응답 스키마 변경.
- 관련 테스트 갱신·신규 테스트.
- `docs/knowledge/product-workflow.md` 스케줄러 섹션, `docs/backend-v0.2.md`
  실행 명령·환경 변수, `docs/decisions/ADR-003-scheduler-approach.md` Follow-up 갱신.

비포함:

- `app/worker/jobs/prices.py`·`app/worker/jobs/news.py` 수집 잡 본체 변경.
- `app/adapters/llm/` 하위 파일 변경.
- 기존 alembic versions 변경.

### Part B — LLM 호출 가드 (BE #209, Decision HHH)

포함:

- `app/adapters/llm/budget.py` — `DailyCallBudget` 신설.
- `app/adapters/llm/exceptions.py` — `LLMBudgetExceededError` 추가.
- `app/core/config.py` — `LLM_DAILY_CALL_LIMIT` 설정 추가.
- `app/adapters/llm/gateway.py` — `call_budget` 파라미터 추가, CLOUD 라우팅 시 consume 호출.
- `app/adapters/factory.py` — cloud 모드이고 limit이 설정된 경우에만 budget 부착.
- 화이트리스트 회귀 테스트, 게이트웨이 상한 테스트.
- `.env.example` 및 `docs/backend-v0.2.md` 환경 변수 문서.

비포함:

- `app/scheduler/`(Part A 산출물) 변경.
- `app/adapters/llm/router.py`·`app/adapters/llm/privacy.py`·프롬프트 지시문 변경.
- 도메인 서비스 비즈니스 로직 변경.

## 3. 구성 요소

### 3.1 `app/scheduler/cron_config.py` (신규)

| 함수 | 책임 |
|---|---|
| `_register_cron_jobs() -> None` | 모듈 임포트 시 `default_scheduler_registry`를 순회하며 `enabled=True`인 항목에 대해 `rq.cron.register(func, "default", cron=...)` 호출 |

스케줄러 프로세스 기동 명령: `uv run rq cron app/scheduler/cron_config.py -u $REDIS_URL`.

### 3.2 `app/scheduler/interface.py` (수정)

`FunctionSchedulerJob`에서 inline `run` 메서드 개념을 제거하고, `ScheduleDefinition`이 worker
잡 함수 참조를 직접 유지하는 프로토콜로 정리한다.

### 3.3 `app/scheduler/registry.py` (수정)

| 잡 이름 | 함수 | cron 표현식 | 비고 |
|---|---|---|---|
| `price_collection` | `collect_prices_job` | `"10 22 * * 1-5"` | 미장 마감 후 UTC 평일 1회 |
| `news_collection` | `collect_news_job` | `"0 * * * *"` | UTC 매시 정각 |

`mock_collection`은 제거한다. cron 표현식은 운영 관찰 후 `registry.py`만 수정해 조정할 수 있다.

### 3.4 `app/scheduler/runner.py` (수정)

| 클래스 | 변경 내용 |
|---|---|
| `ManualSchedulerRunner` | enqueue 전담으로 재작성한다. RQ 큐에 잡 함수를 적재하고 RQ job id를 반환한다. 수집 잡이 `start→succeed/fail`을 스스로 기록하므로 자체 `JobRun` 기록을 제거해 이중 기록을 방지한다. |

### 3.5 `app/api/v1/endpoints/worker.py` (수정)

| 엔드포인트 | 응답 변경 |
|---|---|
| `POST /api/v1/worker/scheduler/jobs/{job_name}/run` | `SchedulerJobRunResponse`의 `job_run_id` 필드를 `job_id: str`(RQ job id)로 교체하고 `status="queued"`를 반환한다. 404·409 오류 계약은 유지한다. |

### 3.6 `app/scheduler/jobs.py` (수정)

`run_mock_collection_job` 함수를 삭제한다.

### 3.7 `app/adapters/llm/budget.py` (신규)

| 클래스 | 메서드 | 시그니처 | 책임 |
|---|---|---|---|
| `DailyCallBudget` | `__init__` | `(self, redis, limit: int)` | Redis 연결과 상한 값을 보관한다 |
| | `consume` | `() -> None` | 키 `llm:cloud_calls:{YYYYMMDD}`(UTC) INCR 후 상한 초과 시 `LLMBudgetExceededError` raise. 첫 INCR 시 TTL 2일 설정. |

### 3.8 `app/adapters/llm/exceptions.py` (수정)

| 예외 클래스 | 상위 타입 | 발생 조건 |
|---|---|---|
| `LLMBudgetExceededError` | `LLMCallError` | 일일 cloud 호출 상한 초과 시 |

### 3.9 `app/core/config.py` (수정)

| 설정 키 | 타입 | 기본값 | 의미 |
|---|---|---|---|
| `LLM_DAILY_CALL_LIMIT` | `int \| None` | `None` | 일일 cloud LLM 호출 상한. `None`이면 무제한. |

### 3.10 `app/adapters/llm/gateway.py` (수정)

| 클래스 | 변경 |
|---|---|
| `LLMGateway` | `__init__`에 `call_budget: DailyCallBudget \| None = None` 추가. `complete_json` 내부에서 `router.resolve(task_type)`가 CLOUD를 반환하고 `call_budget`이 부착된 경우에만 `call_budget.consume()` 호출. |

### 3.11 `app/adapters/factory.py` (수정)

| 함수 | 변경 |
|---|---|
| `get_llm_gateway()` | `LLM_PROVIDER == "cloud"` 이고 `LLM_DAILY_CALL_LIMIT`이 `None`이 아닌 경우에만 `DailyCallBudget`을 생성해 `LLMGateway`에 부착한다. mock·local 모드에는 budget을 부착하지 않는다. |

## 4. Decisions

- **Decision EEE — RQ 내장 cron을 채택하고 `app/scheduler/cron_config.py`를 설정 모듈로
  신설한다.** 모듈 임포트 시점에 `default_scheduler_registry`를 순회하며 `rq.cron.register`를
  호출한다. 스케줄러 프로세스는 `uv run rq cron app/scheduler/cron_config.py -u $REDIS_URL`로
  독립 기동한다. 기각 대안: `rq-scheduler` 패키지(별도 의존성이며 RQ 2.x와 기능이 중복된다),
  APScheduler(ADR-003에서 이미 기각된 방향이다).

- **Decision FFF — 실행 경로를 RQ enqueue로 일원화한다.** 주기 실행(rq cron)과 수동 실행
  endpoint 모두 RQ enqueue만 수행한다. `ManualSchedulerRunner`는 enqueue 담당으로 재작성하고
  자체 `JobRun` 기록을 제거한다. 수집 잡이 `start→succeed/fail`을 스스로 기록하므로 이중
  기록이 발생하기 때문이다. 수동 실행 응답 스키마는 `job_run_id` 대신 RQ job id를 `job_id`로
  반환하도록 변경한다. 내부 ops endpoint라 하위 호환 부담은 없다.

- **Decision GGG — 수집 잡 주기를 UTC 기준으로 확정한다.** `price_collection`
  (collect_prices_job)은 `"10 22 * * 1-5"`, `news_collection`(collect_news_job)은
  `"0 * * * *"`로 등록한다. `mock_collection`·`run_mock_collection_job`은 삭제한다.
  주기 값은 운영 관찰 후 조정할 수 있으며, 조정 시 `registry.py`만 수정하면 된다.

- **Decision HHH — cloud 일일 호출 상한 가드를 `app/adapters/llm/budget.py`의
  `DailyCallBudget`으로 구현한다.** Redis 카운터 키 `llm:cloud_calls:{YYYYMMDD}`(UTC)를
  INCR하고 `LLM_DAILY_CALL_LIMIT`을 초과하면 `LLMBudgetExceededError`를 raise한다.
  게이트웨이는 CLOUD 라우팅 시에만 consume을 호출하며, 팩토리는 cloud 모드이고 limit이
  설정된 경우에만 budget을 부착한다. 기각 대안: 게이트웨이 내부에 카운터를 직접 구현하는 방식
  (budget 개체를 분리하면 테스트 대체성과 재사용성이 높아진다), middleware 레이어 가드(API
  계층 호출에만 적용되어 worker 잡 경로를 커버하지 못한다).

## 5. 테스트

### Part A

- **cron 등록 단언** — `rq.cron.register`를 monkeypatch/fake로 잡아 `cron_config` 모듈을
  임포트하면 `price_collection`·`news_collection` 잡이 기대 cron 표현식과 함께 등록되는지
  단언한다. `AsyncMock`은 사용하지 않는다(코드베이스는 sync).
- **enqueue 경로 단언** — `ManualSchedulerRunner.run(job_name)`을 호출하면
  `rq.Queue.enqueue`가 해당 잡 함수를 대상으로 호출되는지 단언한다.
- **화이트리스트 회귀** — `default_scheduler_registry`에 등록된 잡 함수 집합이
  `{collect_prices_job, collect_news_job}`에 포함됨을 단언한다(§15 — 주기 잡에 LLM 호출
  잡이 혼입되지 않음을 보장한다).

### Part B

- **`DailyCallBudget` 단위 테스트** — fake redis 스텁(INCR·EXPIRE를 흉내 내는 단순 객체)을
  주입해, consume 횟수가 상한 이하일 때 정상 통과하고 초과 시 `LLMBudgetExceededError`가
  raise되는지 검증한다. fakeredis 패키지는 사용하지 않는다.
- **게이트웨이 상한 테스트** — `MockLLMClient`로 조립한 실제 `LLMGateway`에 fake budget
  스텁을 주입하고, CLOUD 라우팅 시 `consume`이 호출되는지, LOCAL 라우팅 시 호출되지
  않는지 각각 단언한다.
- **화이트리스트 회귀(Part A와 동일)** — 두 태스크가 같은 브랜치에서 이어지므로 Part B
  검증 시에도 동일 단언을 통과해야 한다.

## 6. ADR 판단

불필요. Decision EEE는 ADR-003(RQ 계열 주기 스케줄링 확정)의 구체화이며 새로운 아키텍처
방향을 선택하는 것이 아니다. ADR-003에 Follow-up 항목을 추가해 "RQ 내장 cron으로 구체화됨"을
기록하는 것으로 충분하다. Decision HHH는 §16(Redis rate limit 관리)의 적용이며 별도 ADR이
필요한 수준의 방향 전환이 아니다.

## 7. Failure Record 판단

불필요. 이번 작업은 결함 마감이 아니라 계획된 스케줄러 실 경로 연결과 사전 예방적 호출
상한 구현이다.
