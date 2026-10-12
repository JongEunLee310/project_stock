# 08. 백그라운드 실행 — 워커, 스케줄러, 잡

대상 파일: `app/worker/*`, `app/scheduler/*`, `app/domains/jobs/*`,
`app/api/v1/endpoints/worker.py`, `docker-compose.yml`

## 프로세스가 셋이다

`docker-compose.yml`을 보면 같은 이미지로 세 프로세스가 뜹니다.

```yaml
  backend:
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
  worker:
    command: sh -c 'exec rq worker default -u "$$REDIS_URL"'
  scheduler:
    command: sh -c 'exec rq cron app/scheduler/cron_config.py -u "$$REDIS_URL"'
```

01단계에서 `create_app()`에 `lifespan`이 없던 이유가 여기서 드러납니다. **백그라운드 작업은 웹
프로세스 안이 아니라 별도 프로세스에서 돕니다.**

```text
 backend(uvicorn)  ──enqueue──▶  Redis 큐  ──▶  worker(rq worker)
 scheduler(rq cron) ──enqueue──▶     ▲                │
                                     │                ▼
                                 PostgreSQL ◀─────────┘
```

세 프로세스가 **Redis(작업 전달)와 PostgreSQL(데이터)** 을 공유합니다. 코드베이스는 하나이고
진입점만 다릅니다.

`exec`를 쓴 것은 셸이 아니라 실제 프로세스가 PID 1이 되게 해 **컨테이너 종료 신호(SIGTERM)가
워커에 직접 전달**되게 하려는 것입니다. 없으면 셸이 신호를 삼켜 강제 종료됩니다.

`$$REDIS_URL`의 `$$`는 docker-compose가 변수를 치환하지 않고 **컨테이너 안 셸에게 넘기도록**
이스케이프한 것입니다.

## worker/connection.py — 7줄

```python
from redis import Redis
from app.core.config import settings

def get_redis_connection() -> Redis:
    return Redis.from_url(settings.REDIS_URL)
```

06단계의 시장 캐시, 07단계의 LLM 캐시·예산, 그리고 워커 큐가 **모두 이 함수 하나를 씁니다.**
Redis 접속 정보가 코드 전체에서 한 군데에만 있습니다.

호출할 때마다 새 `Redis` 객체를 만들지만, `redis-py`는 내부적으로 커넥션 풀을 갖고 있어 실제
TCP 연결이 매번 생기지는 않습니다. 다만 풀 자체는 객체마다 따로이므로, 고빈도 경로에서는
모듈 수준 싱글턴이 더 낫습니다.

## worker/entrypoint.py — 11줄

```python
from rq import Worker
from app.worker.connection import get_redis_connection

def main() -> None:
    Worker(["default"], connection=get_redis_connection()).work()
```

**RQ(Redis Queue)** 를 씁니다. Celery보다 훨씬 가볍고, 브로커가 Redis 하나뿐이며 설정이 거의
없습니다. `["default"]`는 감시할 큐 이름 목록입니다.

실제 compose는 이 파일 대신 `rq worker default` CLI를 씁니다. 같은 일을 하며, CLI 쪽이 재시작·로그
옵션을 붙이기 쉬워 그쪽을 택한 것으로 보입니다.

`.work()`는 무한 루프로 큐를 감시하다 잡이 오면 실행합니다. **RQ 워커는 잡마다 프로세스를
fork**하므로, 잡이 죽어도 워커는 살아남고 메모리 누수가 누적되지 않습니다.

## 잡 함수의 표준 골격

`app/worker/jobs/` 아래 9개 파일이 모두 같은 형태입니다.

```python
def collect_prices_job(symbols: list[str] | None = None, range_value: str = "3M") -> None:
    db = SessionLocal()                      # ① 세션을 직접 만든다
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        targets = PriceUniverseResolver(db).resolve()
        job_run = job_run_service.start("price_collection", {...})   # ② 시작 기록
        job_run_id = job_run.id
        PriceIngestionService(db).collect_and_save(...)              # ③ 실제 작업
        job_run_service.succeed(job_run.id)                          # ④ 성공 기록
        return None
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))               # ⑤ 실패 기록
        raise                                                        # ⑥ 다시 던진다
    finally:
        db.close()                                                   # ⑦ 반드시 닫는다
```

### ① 세션을 직접 만든다

02단계의 `Depends(get_db)`는 FastAPI 안에서만 동작합니다. 워커에는 요청도 의존성 주입도 없으므로
`SessionLocal()`을 직접 호출하고 `finally`에서 닫습니다. **`get_db`가 하던 일을 손으로 하는 것**과
같습니다.

이것이 06단계에서 어댑터 팩토리를 `Depends`가 아닌 일반 함수로 만든 이유입니다. `get_llm_gateway()`,
`get_price_series_provider()`가 HTTP 안팎에서 똑같이 호출됩니다.

### ②④⑤ JobRun 기록

```python
class JobRun(Base, TimestampMixin):
    job_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))       # running / success / failed
    started_at / finished_at
    error_message: Mapped[str | None]
    metadata_: Mapped[dict | None]                        # JSON
```

**모든 백그라운드 실행이 DB에 흔적을 남깁니다.** 워커는 사용자가 보고 있지 않으므로, 실패해도
아무도 모르는 상태가 가장 위험합니다. `GET /api/v1/job-runs`로 이력을 조회할 수 있습니다.

`job_run_id`를 `try` 밖에서 `None`으로 초기화하는 이유는 **`start()` 자체가 실패할 수 있기**
때문입니다. DB가 죽어 있으면 `job_run`이 없으므로 `except`에서 `job_run.id`를 참조하면 `NameError`가
납니다. 그래서 `if job_run_id is not None` 가드를 둡니다.

### ⑥ 예외를 다시 던지는 이유

```python
    except Exception as exc:
        job_run_service.fail(job_run_id, _error_message(exc))
        raise
```

DB에 실패를 기록한 **뒤에도 예외를 다시 던집니다.** RQ가 잡 실패를 인지해 실패 큐(failed job
registry)에 넣게 하려는 것입니다. 삼키면 RQ는 성공으로 간주하고, 재시도·모니터링이 동작하지
않습니다. **기록과 전파는 별개**입니다.

### 부분 실패 처리

```python
        for watchlist_id in watchlist_ids:
            try:
                result = service.run(watchlist_id)
                failures.extend(...)
            except Exception as exc:
                db.rollback()
                failures.append({"watchlist_id": watchlist_id, "error": _error_message(exc)})
                logger.warning("watchlist analysis failed: watchlist_id=%s", watchlist_id, exc_info=True)
        if failures:
            _record_partial_failures(job_run, failures)
        job_run_service.succeed(job_run.id)
```

05단계 수집 파이프라인과 같은 원칙 — **항목 단위로 예외를 격리**합니다. 여기서는 한 걸음 더
나아가 실패 목록을 `metadata_["partial_failures"]`에 저장하고, **전체는 `succeed`로 표시**합니다.

"10개 중 2개 실패"를 실패로 볼지 성공으로 볼지는 판단인데, 이 프로젝트는 성공 + 상세 기록을
택했습니다. 다만 상태만 보는 모니터링에서는 부분 실패가 보이지 않으므로 `metadata_`까지 봐야
합니다.

```python
                db.rollback()
```

**루프 안의 `rollback()`이 중요합니다.** 03단계에서 본 대로 PostgreSQL은 트랜잭션에서 에러가 나면
그 트랜잭션을 aborted로 만들어 이후 모든 쿼리를 거부합니다. 롤백하지 않으면 3번째 관심목록이
실패한 뒤 4~10번째가 전부 연쇄 실패합니다.

```python
def _error_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail
    return str(exc)
```

`AppException`이면 `detail`(한국어 메시지)을, 아니면 `str(exc)`를 씁니다. service 계층을 그대로
재사용하다 보니 워커에서도 `AppException`이 올라오는데, 그때 더 읽기 좋은 메시지를 남기려는
처리입니다.

### `metadata_` 갱신 방식

```python
        job_run.metadata_ = {"watchlist_ids": watchlist_ids}
        db.commit()

def _record_partial_failures(job_run: JobRun, failures: list[dict[str, object]]) -> None:
    metadata = dict(job_run.metadata_ or {})
    metadata["partial_failures"] = failures
    job_run.metadata_ = metadata
```

**dict를 복사해 통째로 재대입합니다.** `job_run.metadata_["key"] = value`처럼 제자리 수정하면
SQLAlchemy가 변경을 감지하지 못합니다. JSON 컬럼은 기본적으로 **객체 동일성으로 변경을 추적**하기
때문입니다(`MutableDict`를 쓰면 제자리 수정도 감지되지만 이 프로젝트는 쓰지 않습니다).

이 프로젝트에서 JSON 컬럼을 갱신할 때 반드시 지켜야 하는 관용구입니다.

### 큐에 넣는 안전한 방법

```python
def enqueue_watchlist_analysis_safe(watchlist_id: int) -> None:
    try:
        queue = Queue("default", connection=get_redis_connection())
        queue.enqueue(analyze_watchlist_job, watchlist_id)
    except Exception:
        logger.warning("failed to enqueue watchlist analysis: watchlist_id=%s",
                       watchlist_id, exc_info=True)
```

04단계에서 예고한 `_safe`의 구현입니다. **Redis가 죽어도 관심목록 추가는 성공**해야 하므로 예외를
삼킵니다. 부가 작업이 주 작업을 망가뜨리지 않게 하는 패턴입니다.

`queue.enqueue(analyze_watchlist_job, watchlist_id)`에서 **함수 객체와 인자를 넘깁니다.** RQ는
함수를 `모듈경로.함수명` 문자열로 직렬화하고, 인자는 pickle로 직렬화해 Redis에 넣습니다. 워커가
꺼내서 import하고 실행합니다.

여기서 나오는 제약이 중요합니다.

- **인자는 pickle 가능해야 합니다.** ORM 객체나 DB 세션을 넘길 수 없습니다. 그래서 모든 잡이
  `watchlist_id: int`, `symbols: list[str]`처럼 **원시 타입 식별자**만 받습니다.
- **워커가 그 함수를 import할 수 있어야 합니다.** 같은 코드베이스를 배포하므로 성립합니다.
- **잡 함수의 시그니처를 바꾸면 큐에 남아 있던 잡이 깨집니다.** 배포 시 주의할 점입니다.

## scheduler/ — 시간표

### interface.py — Protocol로 정의한 잡

```python
SchedulerJobFunc = Callable[..., None]

class SchedulerJob(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def func(self) -> SchedulerJobFunc: ...

@dataclass(frozen=True)
class FunctionSchedulerJob:
    name: str
    func: SchedulerJobFunc
```

07단계 `RedisCounter`와 같은 **`Protocol`** 기법입니다. `name`과 `func` 속성만 있으면 무엇이든
스케줄러 잡이 될 수 있습니다. `FunctionSchedulerJob`은 `Protocol`을 상속하지 않는데도 조건을
만족하므로 그대로 쓰입니다 — 구조적 타이핑의 특징입니다.

`SchedulerJobFunc = Callable[..., None]`은 **반환값이 없어야 한다**는 계약입니다. 잡의 결과는
반환이 아니라 DB(`JobRun`)에 남습니다.

### registry.py — 시간표 데이터

```python
@dataclass(frozen=True)
class ScheduleDefinition:
    job: SchedulerJob
    cron: str
    enabled: bool = True

default_scheduler_registry = SchedulerRegistry([
    ScheduleDefinition(job=FunctionSchedulerJob(name="price_collection", func=collect_prices_job),
                       cron="10 22 * * 1-5", enabled=True),
    ScheduleDefinition(job=FunctionSchedulerJob(name="analysis_us_session", func=analyze_all_watchlists_job),
                       cron="0 13-21 * * 1-5", enabled=settings.ANALYSIS_SCHEDULE_ENABLED),
    ...
])
```

9개 스케줄이 한 리스트에 모여 있습니다. **시간표를 코드가 아니라 데이터로 표현**했기 때문에
전체를 한눈에 볼 수 있습니다.

cron 표현식을 읽어보면 도메인 지식이 드러납니다(모두 **UTC 기준**).

| 잡 | cron | 의미 |
| --- | --- | --- |
| `price_collection` | `10 22 * * 1-5` | 평일 22:10 UTC = **한국 07:10**, 미국 장 마감 후 |
| `analysis_kr_open` | `0 23 * * 0-4` | 일~목 23:00 UTC = **한국 08:00**, 장 시작 전 |
| `analysis_kr_main` | `0 0-7 * * 1-5` | 평일 09:00~16:00 KST **매시간**, 한국 장중 |
| `analysis_us_session` | `0 13-21 * * 1-5` | 미국 장중 매시간 |
| `news_collection` | `0 * * * *` | 매시 정각 |
| `alert_evaluation` | `*/5 * * * *` | 5분마다 |
| `signal_snapshot` | `30 11 * * 1-5` | 평일 11:30 UTC |

`0-4`(일~목)와 `1-5`(월~금)의 차이가 핵심입니다. **UTC 23시는 한국의 다음 날 오전 8시**이므로,
한국 기준 월~금 아침에 돌리려면 UTC로는 일~목이어야 합니다. 타임존 변환을 cron에 녹인 형태이며,
읽을 때 가장 헷갈리는 지점입니다.

```python
            enabled=settings.ANALYSIS_SCHEDULE_ENABLED,
```

**enabled가 설정값과 연결**되어 있습니다. LLM을 호출하는 분석 잡과 알림 엔진은 기본으로 꺼져
있어(`ANALYSIS_SCHEDULE_ENABLED=False`, `ALERT_ENGINE_ENABLED=False`) 개발 환경에서 비용이 나가지
않습니다. 1단계에서 본 설정 플래그가 여기서 쓰입니다.

`analyze_all_watchlists_job` 하나를 **네 개의 스케줄이 공유**합니다. 이름만 다르고 함수는 같습니다.
잡을 시장 시간대별로 나눠 이름을 붙이면 로그와 수동 실행에서 어느 시간대의 실행인지 구분됩니다.

### cron_config.py — 12줄

```python
from rq import cron as rq_cron
from app.scheduler.registry import default_scheduler_registry

def _register_cron_jobs() -> None:
    for schedule in default_scheduler_registry.list():
        if schedule.enabled:
            rq_cron.register(schedule.job.func, "default", cron=schedule.cron)

_register_cron_jobs()
```

**모듈 최하단에서 함수를 즉시 호출**합니다. `rq cron app/scheduler/cron_config.py`가 이 파일을
import하는 순간 등록이 끝나는 구조입니다. 1단계의 `settings = Settings()`와 같은 "import가 곧
실행" 패턴입니다.

`enabled=False`인 스케줄은 **아예 등록되지 않습니다.** 설정을 바꾸면 스케줄러 프로세스를
재시작해야 반영됩니다.

### runner.py — 수동 실행

```python
class ManualSchedulerRunner:
    def run(self, job_name: str) -> SchedulerRunResult:
        schedule = self.registry.get(job_name)
        if schedule is None:
            raise SchedulerJobNotFoundError(job_name)
        if not schedule.enabled:
            raise SchedulerJobDisabledError(job_name)
        queued_job = self.queue.enqueue(schedule.job.func)
        return SchedulerRunResult(job_name=..., job_id=str(queued_job.id), status="queued")
```

**cron 시각을 기다리지 않고 즉시 한 번 실행**하는 통로입니다. 운영에서 "지금 가격 수집을 돌려봐야
할 때"와 개발에서 동작을 확인할 때 씁니다.

`enabled=False`면 거부하는 것이 중요합니다. 설정으로 꺼둔 잡을 API로 우회 실행할 수 없습니다.

```python
class SchedulerQueue(Protocol):
    def enqueue(self, f: SchedulerJobFunc) -> QueuedJob: ...
```

여기도 `Protocol`입니다. 덕분에 테스트에서 RQ 없이 가짜 큐로 검증할 수 있습니다. **이 프로젝트는
외부 인프라(Redis)에 닿는 지점마다 `Protocol`을 세워 테스트 가능하게 만듭니다.**

## endpoints/worker.py — 잡을 HTTP로 트리거

```python
def enqueue_news_job(payload: NewsJobRequest) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(collect_news_job, payload.symbols)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))
```

**즉시 `job_id`를 돌려주고 끝냅니다.** 결과를 기다리지 않는 비동기 API이며, 클라이언트는
`job_id`로 나중에 상태를 조회합니다.

```python
class NewsJobRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)
```

`min_length=1`로 **빈 리스트를 거부**합니다. 없으면 아무 일도 안 하는 잡이 큐에 쌓입니다.

### Redis로 구현한 레이트 리밋

```python
    rate_limit_key = f"rate_limit:analysis_manual:{current_user.id}"
    if not connection.set(rate_limit_key, "1", nx=True, ex=60):
        raise AppException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="분석 요청은 60초에 한 번만 실행할 수 있습니다.",
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            headers={"Retry-After": "60"},
        )
```

**`SET key value NX EX 60`** 이 레이트 리밋의 전부입니다. `nx=True`는 "키가 없을 때만 설정"이므로,
이미 있으면 `False`가 돌아옵니다. 원자적 연산이라 동시 요청에서도 정확합니다.

사용자별 키(`{current_user.id}`)이므로 사용자마다 따로 계산되고, `ex=60`으로 60초 뒤 자동
소멸합니다. 별도 정리 작업이 필요 없습니다.

`headers={"Retry-After": "60"}`는 1단계에서 `AppException`에 `headers` 필드를 둔 이유이자, 02단계
`WWW-Authenticate`에 이은 두 번째 활용 사례입니다.

LLM을 호출하는 무거운 잡에만 이 제한이 걸려 있습니다 — 비용이 나가는 경로를 우선 보호한 것입니다.

### 이 파일만 규칙을 벗어난다

```python
    except SchedulerJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="scheduler job not found") from exc
```

**`AppException`이 아니라 FastAPI의 `HTTPException`을 씁니다.** 1단계에서 확인한 대로 이 경로는
FastAPI 기본 핸들러를 타므로 응답이 `{"detail": "..."}`이 되어 **공통 봉투가 깨집니다.** 같은
파일의 429는 `AppException`을 쓰는데 여기만 다릅니다.

`ErrorCode`에 스케줄러 관련 코드를 추가하고 `AppException`으로 바꾸면 일관성이 회복됩니다. 코드를
읽을 때 이 엔드포인트만 응답 형식이 다르다는 점을 기억해 두면 됩니다.

### 인증이 일관되지 않다

| 엔드포인트 | 인증 |
| --- | --- |
| `/jobs/analysis`, `/jobs/llm-analysis` | `get_current_user` 필요 |
| `/jobs/news`, `/jobs/valuation`, `/jobs/earnings` | **없음** |
| `/scheduler/jobs/{name}/run` | **없음** |

LLM 비용이 드는 것만 보호되어 있습니다. 나머지도 외부 API를 호출하고 DB에 쓰므로, 인증 없이
누구나 트리거할 수 있는 상태는 위험합니다. 운영 배포 시 점검해야 할 지점입니다.

## 전체 흐름 두 가지

### 스케줄 트리거

```text
scheduler 프로세스 (rq cron)
  cron_config.py import 시 registry의 enabled 스케줄을 rq_cron에 등록
    ↓ cron 시각 도달 (예: 22:10 UTC)
  Redis "default" 큐에 collect_prices_job 적재
    ↓
worker 프로세스가 꺼냄 → fork
  SessionLocal() 생성
  JobRun(status=running) 기록
  PriceUniverseResolver로 대상 결정 → provider 호출 → raw 저장 → 검증 → upsert
  JobRun(status=success) 갱신
  db.close()
```

### 사용자 트리거

```text
POST /api/v1/watchlists/{id}/items
  WatchlistService.add_item → INSERT + COMMIT
  enqueue_watchlist_analysis_safe(watchlist_id)   ← 실패해도 무시
    ↓ Redis 큐
worker: analyze_watchlist_job(watchlist_id)
  JobRun(running) → WatchlistAnalysisService.run (LLM 호출 포함)
  → 부분 실패는 metadata_["partial_failures"]에 기록 → JobRun(success)
```

## 이 단계에서 확인한 프로젝트 규칙

1. 무거운 작업·외부 호출·LLM은 워커로 보낸다. FastAPI `BackgroundTasks`를 쓰지 않는다.
2. 잡 함수는 `SessionLocal()`로 세션을 직접 만들고 `finally`에서 닫는다.
3. 모든 잡은 `JobRunService`로 시작·성공·실패를 기록하고, **기록 후 예외를 다시 던진다.**
4. 잡 인자는 pickle 가능한 원시 타입만 쓴다. ORM 객체·세션을 넘기지 않는다.
5. 반복 작업은 항목 단위로 예외를 격리하고, 실패 시 `db.rollback()` 후 계속한다. 부분 실패는
   `metadata_["partial_failures"]`에 남긴다.
6. JSON 컬럼은 dict를 복사해 통째로 재대입한다. 제자리 수정은 감지되지 않는다.
7. 스케줄은 `registry.py` 한 곳에 데이터로 모으고, cron은 UTC로 쓴다. 비용이 드는 잡은
   `enabled=settings.XXX_ENABLED`로 기본 차단한다.
8. 외부 인프라 경계는 `Protocol`로 추상화해 테스트에서 대체 가능하게 한다.
9. 부가 작업 큐 적재는 `_safe` 래퍼로 감싸 주 기능에 영향을 주지 않게 한다.

## 알아둘 만한 개선 지점

- `run_scheduler_job_once`가 `HTTPException`을 써서 공통 응답 봉투를 깬다.
- `/jobs/news`·`/jobs/valuation`·`/jobs/earnings`·`/scheduler/.../run`에 인증이 없다.
- 부분 실패가 `JobRun.status="success"`로 남아 상태만 보는 모니터링에서는 드러나지 않는다.
- `get_redis_connection()`이 호출마다 새 `Redis` 객체를 만든다(풀은 객체별로 분리).

## 다음 단계로 이어지는 질문

- `analyze_all_watchlists_job`이 부르는 `WatchlistAnalysisService`는 무엇을 만드는가? (09단계)
- `evaluate_alert_rules_job`의 알림 엔진은 어떤 규칙으로 발화하는가? (09단계)
- `snapshot_signal_states_job`이 남기는 스냅샷은 어디에 쓰이는가? (09단계)
