# ADR-003: Scheduler Approach

## Status

Accepted

## Context

Issue #64는 뉴스·공시·시세 데이터를 주기적으로 수집할 scheduler 구조의 초안을 요구한다. 현재 백엔드는 RQ 기반 worker(`app/worker/*`)와 `job_runs` 실행 이력 도메인, 수동 enqueue endpoint(`POST /jobs/*`)를 가지고 있으나, 주기적 실행(cron-like) 구조와 공식 Job interface는 없다. 즉 "작업을 큐에 넣고 worker가 실행"하는 인프라는 있지만 "특정 시각/주기에 자동으로 큐에 투입"하는 시간 트리거가 빠져 있다.

### RQ란 무엇인가

**RQ(Redis Queue, PyPI `rq`)**는 Redis를 브로커로 사용하는 파이썬 백그라운드 작업 큐 라이브러리다. 동작은 단순하다.

- **enqueue**: 웹 프로세스(FastAPI)가 "이 함수를 나중에 실행"을 요청하면, RQ는 함수의 임포트 경로와 인자를 직렬화해 Redis 큐(List)에 push하고 `job_id`를 즉시 반환한다. 요청은 작업 완료를 기다리지 않는다.
- **worker**: 별도 프로세스(`rq worker`)가 Redis를 `BLPOP`으로 감시하다 작업을 꺼내, 해당 함수를 임포트해 실행한다. 기본적으로 작업마다 자식 프로세스를 fork해 격리하며, 결과/실패 상태를 Redis에 다시 기록한다.
- **상태 추적**: job은 `queued → started → finished/failed`를 거치고, 실패 시 FailedJobRegistry에 남아 재시도·조회가 가능하다. 본 프로젝트의 `job_runs` 도메인과 `/jobs`·`/worker` 엔드포인트가 이 상태를 노출·관리한다.

여기서 "비동기"는 asyncio(`async`/`await`)의 동시성이 아니라 **요청-응답에서 무거운 작업을 떼어내 다른 프로세스로 격리**하는 백그라운드 처리를 뜻한다. `async def`가 "한 프로세스 안에서 대기 시간을 효율적으로 쓰는 것"이라면, RQ는 "작업 자체를 worker 프로세스로 던져 웹 요청과 분리하는 것"이다. 두 개념은 공존한다.

### 왜 RQ를 쓰는가 (현 스택 기준)

- **오래 걸리는 작업 분리**: LLM 분석·뉴스 수집은 수 초~수십 초가 걸려 요청 안에서 처리하면 HTTP 타임아웃·UX 악화를 부른다. enqueue 후 즉시 `job_id`를 반환하고 worker가 처리한다.
- **프로세스 격리**: 무겁거나 불안정한 작업이 크래시해도 웹 서버는 영향을 받지 않는다.
- **재시도·추적**: 실패 작업이 레지스트리에 남아 재시도·상태 조회가 가능하다.
- **인프라 최소화**: 이미 Redis가 스택에 있어 추가 컴포넌트 없이 동작한다. Celery 대비 설정·학습 비용이 낮고, MVP 규모(작업 종류 소수)에 과하지 않다.

RQ 자체에는 시간 트리거가 없으므로, 주기 실행을 위해서는 별도 스케줄러가 필요하다 — 이것이 본 ADR이 결정하는 지점이다.

## Decision

**기존 RQ/Redis 스택 위에 rq-scheduler 계열의 주기 스케줄링을 도입한다.** 이미 RQ·Redis·worker가 갖춰져 있으므로 스택을 늘리지 않고 시간 트리거만 보태는 최소 추가가 된다.

단, Issue #64는 초안 범위이므로 이번 단계에서는 실제 주기 등록을 mock으로 두고 Job interface·스케줄 구조만 확정한다. 실제 트리거 등록·운영 적용은 후속 버전에서 전환한다.

## Alternatives

- **rq-scheduler 계열 (채택)**: 기존 RQ/Redis 인프라 재사용. 운영 컴포넌트 추가 최소, 학습 비용 낮음. 스케줄러 프로세스 관리가 추가된다.
- **APScheduler**: 앱 프로세스 내 스케줄링으로 단순하나, RQ worker와 실행 역할이 중복되고 다중 인스턴스/인메모리 구성에서 중복 실행 위험이 있다.
- **외부 cron / 오케스트레이터(k8s CronJob 등)**: 앱과 분리되어 운영은 단순하나 인프라에 의존하고 배포 환경 제약이 크다. 앱 코드만으로 재현·테스트하기 어렵다.

## Consequences

- Redis/RQ 의존을 그대로 활용해 학습·운영 비용이 낮다. 대신 scheduler 프로세스를 worker와 함께 관리해야 한다.
- 작업 함수가 동기 `def`로 worker에서 실행되는 기존 패턴을 유지하므로, 스케줄 트리거만 추가하면 기존 job 정의를 재사용할 수 있다.
- 초안 단계에서는 기술 확정만 하고 인터페이스를 고정 — 후속 버전에서 mock을 실제 트리거로 교체한다.
- rq-scheduler는 RQ 위의 얇은 확장이므로, 향후 요구가 커지면(복잡한 워크플로·라우팅·정교한 재시도) Celery 등으로의 이전을 재검토할 수 있다.

## Follow-up

- 실제 주기 등록·운영 적용(후속 버전).
- 설계 044에 본 결정(rq-scheduler 채택) 반영.

## Related Documents

- Issue #64
- `docs/designs/044-scheduler-skeleton.md`
- `docs/designs/011-worker-background-job.md`, `docs/designs/012-job-runs-domain.md`
