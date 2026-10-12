# 12. 엔드투엔드 추적

지금까지 층별로 본 것을 **실제 흐름 두 개**로 이어 붙입니다. 하나는 사용자 요청, 하나는 백그라운드
잡입니다.

## 추적 1 — `POST /api/v1/watchlists/1/items`

관심목록에 종목을 추가하는 요청입니다. 프로세스 하나 안에서 끝나지 않고 마지막에 워커로
이어집니다.

### 1) uvicorn → 미들웨어 스택 (01단계)

```text
await app(scope, receive, send)
  ServerErrorMiddleware        Exception 핸들러 소유
    CORSMiddleware             Origin 검사
      RequestIdMiddleware      X-Request-ID 생성 → request.state + ContextVar
        ExceptionMiddleware    AppException·422 핸들러 소유
          router
```

`RequestIdMiddleware.dispatch`가 요청 ID를 두 군데(`request.state`, `ContextVar`)에 심고
`time.perf_counter()`를 기록합니다. 이후 이 요청에서 나오는 모든 로그에 `request_id`가 자동으로
붙습니다.

### 2) 라우팅 (02단계)

```text
FastAPI app
  → api_router (prefix="/api/v1")
    → watchlists.router (prefix="/watchlists")
      → @router.post("/{watchlist_id}/items")
```

경로 파라미터 `watchlist_id: int`가 문자열 `"1"`에서 `1`로 변환됩니다. 실패하면 여기서 422.

### 3) 의존성 해석 (02단계)

```text
add_watchlist_item(watchlist_id, data, db=Depends(get_db), current_user=Depends(get_current_user))
  ├─ get_db          → SessionLocal() 생성 (yield 앞)
  └─ get_current_user
       ├─ oauth2_scheme → Authorization 헤더에서 Bearer 토큰 추출
       ├─ decode_token  → 서명·만료 검증, type == "access" 확인
       └─ SELECT user   ← get_db가 만든 같은 세션 (요청 스코프 캐싱)
```

세션은 **하나만** 만들어집니다. 토큰이 없거나 잘못됐으면 `AppException(401)`이 여기서 발생하고,
엔드포인트 본문은 실행되지 않습니다.

### 4) 본문 검증 (02·04단계)

```python
class WatchlistItemCreate(BaseModel):
    asset_id: int
    priority: int = 0
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    memo: str | None = None
```

Pydantic이 JSON을 검증합니다. 실패하면 `RequestValidationError` → `ExceptionMiddleware` →
`validation_exception_handler` → 422 + `{"error": {"code": "VALIDATION_ERROR", "fields": [...]}}`.

### 5) 엔드포인트 (04단계)

```python
def add_watchlist_item(watchlist_id, data, db, current_user):
    item = WatchlistService(db).add_item(watchlist_id, current_user.id, data)
    enqueue_watchlist_analysis_safe(watchlist_id)
    return success(item)
```

`def`(async 아님)이므로 **anyio 스레드풀에서 실행**됩니다. 동기 SQLAlchemy가 블로킹해도 이벤트
루프는 다른 요청을 계속 처리합니다.

`current_user`가 아니라 `current_user.id`를 넘깁니다 — service는 인증 방식을 모릅니다.

### 6) service (04단계)

```python
    def add_item(self, watchlist_id, user_id, data) -> WatchlistItemResponse:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)   # 404 / 403
        if self.asset_repo.get_by_id(data.asset_id) is None:
            raise AppException(404, ..., ErrorCode.ASSET_NOT_FOUND)
        if self.item_repo.get_by_watchlist_asset(watchlist.id, data.asset_id):
            raise AppException(400, ..., ErrorCode.WATCHLIST_ITEM_DUPLICATE)
        try:
            item = self.item_repo.create(...)
        except IntegrityError as exc:
            raise AppException(400, ..., ErrorCode.WATCHLIST_ITEM_DUPLICATE) from exc
        return WatchlistItemResponse.model_validate(item)
```

검사 순서가 곧 응답 우선순위입니다. **소유권 → 대상 존재 → 중복 → 생성.**

### 7) repository → DB (03·04단계)

```python
        self.db.add(item)
        try:
            self.db.commit()      # INSERT + 트랜잭션 확정
        except IntegrityError:
            self.db.rollback()    # PostgreSQL aborted 상태 해제
            raise
        self.db.refresh(item)     # DB가 채운 id, created_at 읽기
```

`uq_watchlist_items_asset` 복합 유니크 제약이 동시 요청 경합의 최종 방어입니다.

### 8) 워커 큐 (08단계)

```python
def enqueue_watchlist_analysis_safe(watchlist_id: int) -> None:
    try:
        queue = Queue("default", connection=get_redis_connection())
        queue.enqueue(analyze_watchlist_job, watchlist_id)
    except Exception:
        logger.warning(...)
```

**커밋 이후**에 큐에 넣습니다. 워커가 즉시 집어가도 행이 보입니다. Redis가 죽어 있어도 예외를
삼키므로 이 요청은 성공합니다.

### 9) 응답 (01단계)

```text
success(item) → ApiResponse[WatchlistItemResponse]
  → response_model 검증 + 필드 필터링 + JSON 직렬화
  → created_at은 UtcDatetime PlainSerializer로 "2026-07-31T09:00:00Z"
  → status_code=201
```

### 10) 정리

```text
get_db의 finally      → db.close()
RequestIdMiddleware   → 응답 헤더에 X-Request-ID 부착
                      → finally에서 latency 로그 + ContextVar reset
CORSMiddleware        → Access-Control-Allow-Origin 부착
```

**응답 직렬화가 끝난 뒤에 세션이 닫힙니다.** 그래서 ORM 객체를 다뤄도 안전합니다.

### 실패 경로 요약

| 상황 | 처리 위치 | 응답 | CORS 헤더 |
| --- | --- | --- | --- |
| 토큰 없음/만료 | `deps.get_current_user` | 401 `AUTH_INVALID_TOKEN` | 붙음 |
| 본문 형식 오류 | FastAPI 검증 | 422 `VALIDATION_ERROR` | 붙음 |
| 남의 관심목록 | `_get_owned_watchlist` | 403 `WATCHLIST_FORBIDDEN` | 붙음 |
| 종목 없음 | service | 404 `ASSET_NOT_FOUND` | 붙음 |
| 중복 | service / DB 제약 | 400 `WATCHLIST_ITEM_DUPLICATE` | 붙음 |
| **테이블 없음(마이그레이션 누락)** | ServerErrorMiddleware | 500 `INTERNAL_ERROR` | **안 붙음** |

마지막 줄이 실무에서 가장 헷갈리는 경우입니다. 브라우저에는 `Failed to fetch`로만 보이므로
**서버 로그를 봐야 원인을 알 수 있습니다.**

## 추적 2 — 스케줄 잡 `analyze_all_watchlists_job`

프로세스 세 개를 넘나드는 흐름입니다.

### 1) scheduler 프로세스 (08단계)

```text
rq cron app/scheduler/cron_config.py
  → import 시 registry의 enabled 스케줄을 rq_cron에 등록
  → "analysis_kr_main" (cron="0 0-7 * * 1-5", 한국 09~16시)
     단, enabled=settings.ANALYSIS_SCHEDULE_ENABLED — 기본 False
```

기본 설정에서는 **등록조차 되지 않습니다.** LLM 비용이 나가는 잡이므로 명시적으로 켜야 합니다.

### 2) Redis 큐 → worker 프로세스

```text
cron 시각 도달 → "default" 큐에 함수 경로 + 인자 적재
  → rq worker가 꺼내 fork → analyze_all_watchlists_job() 실행
```

### 3) 잡 골격 (08단계)

```python
def analyze_all_watchlists_job() -> None:
    db = SessionLocal()                       # 의존성 주입 없음
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start("all_watchlists_analysis", {"watchlist_ids": []})
        job_run_id = job_run.id
        watchlist_ids = list(db.scalars(select(Watchlist.id).order_by(Watchlist.id)))
        job_run.metadata_ = {"watchlist_ids": watchlist_ids}   # dict 통째 재대입
        db.commit()
        ...
```

`JobRun(status="running")`이 먼저 기록되므로, 잡이 도중에 죽어도 "시작했는데 안 끝난 것"이 DB에
남습니다.

### 4) 관심목록 단위 격리 (08단계)

```python
        for watchlist_id in watchlist_ids:
            try:
                result = service.run(watchlist_id)
                failures.extend(...)
            except Exception as exc:
                db.rollback()                 # aborted 트랜잭션 해제
                failures.append({"watchlist_id": watchlist_id, "error": _error_message(exc)})
```

### 5) 분석 service (04·07·09단계가 모두 만나는 지점)

```python
class WatchlistAnalysisService:
    def __init__(self, db, gateway: LLMGateway, news_adapter: NewsAdapter) -> None:
        self.watchlist_repo = ...      # 04단계
        self.raw_news_repo = ...       # 05단계와 같은 raw 보존 구조
        self.news_analysis = NewsAnalysisService(db, gateway)     # 07단계
        self.thesis_analysis = ThesisAnalysisService(db, gateway) # 07단계
        self.report_service = ResearchReportService(db)
        self.alert_service = AlertService(db)                     # 09단계
```

**생성자 주입**입니다. 06단계에서 본 두 방식(팩토리 직접 호출 vs 생성자 주입) 중 이쪽을 택해
테스트에서 가짜 게이트웨이·어댑터를 넣기 쉽게 만들었습니다.

```python
    def _process_asset(self, asset: Asset, user_id: int) -> _AssetAnalysisResult:
        collected_results = self.news_adapter.fetch_query(asset.name, market)   # ① 외부 수집
        for result in collected_results:
            saved_event = raw_news_service.save_with_symbol(result, asset.symbol, market)
            if saved_event is not None:
                new_results.append(result)                                       # ② 신규만 통과
        news_items = self._create_new_items(asset, new_results)                  # ③ 정규화 저장
        thesis = self.thesis_repo.get_latest_by_asset(asset.id, user_id)

        for news_item in news_items:
            summary_result = self.news_analysis.summarize(news_item.id)          # ④ LLM 요약
            self.db.refresh(news_item)
            conflict_result = self._analyze_conflict(news_item, thesis)          # ⑤ LLM 논거 충돌
            self._create_report(asset.id, news_item, summary_result, thesis, conflict_result)
            signals = RuleEngine(default_rules(), SignalRepository(self.db)).run(
                RuleContext(asset_id=asset.id, news_item=news_item,
                            thesis=thesis, conflict_result=conflict_result))     # ⑥ 시그널 판정
            for signal in signals:
                if self.alert_service.create_alert(user_id, signal) is not None: # ⑦ 알림 생성
                    created_alerts += 1
```

**한 종목에 대해 수집 → 원본 보존 → 정규화 → LLM 분석 → 규칙 판정 → 알림까지 이어집니다.**
이 프로젝트의 모든 층이 이 메서드에서 만납니다.

②의 `save_with_symbol`이 `None`을 돌려주면 **이미 본 뉴스**입니다. 05단계 `RawPriceService.save_raw`와
같은 해시 기반 중복 제거이며, **이미 분석한 뉴스에 LLM을 다시 호출하지 않는** 비용 방어입니다.

④⑤가 07단계의 `LLMGateway`를 거칩니다 — 개인정보 게이트 → 캐시 → 예산 → OpenAI 호출.

⑥의 `RuleEngine`은 09단계 `alert_engine`과 다른 별도 엔진입니다. `default_rules()`가 **코드에
정의된 규칙**을 쓰는 반면, `alert_engine`은 **DB에 저장된 사용자 규칙**을 씁니다. 시스템 판정과
사용자 알림이 분리된 구조입니다.

`self.db.refresh(news_item)`은 `summarize`가 같은 세션에서 그 행을 갱신했기 때문에 필요합니다.

### 6) 마무리 (08단계)

```python
        if failures:
            _record_partial_failures(job_run, failures)   # metadata_에 기록
        job_run_service.succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, _error_message(exc))
        raise                                             # RQ가 실패를 인지하도록
    finally:
        db.close()
```

**부분 실패는 `success` + `metadata_["partial_failures"]`** 로 남습니다. 상태만 보는 모니터링에서는
드러나지 않는 점을 기억해야 합니다.

### 7) 결과가 사용자에게 보이는 경로

```text
worker가 만든 Signal
  → 사용자가 GET /api/v1/watchlists/1/items?expand=asset 호출
  → WatchlistService.list_items_expanded
  → signal_repo.active_signal_types_by_asset(asset_ids)
  → resolve_watchlist_status(active_types)     ← 09단계 우선순위 튜플
  → WatchlistItemExpandedResponse.status = "RISK_ALERT"
```

**백그라운드가 만든 판정이 관심목록의 상태 배지로 나타납니다.** 비동기 작업과 사용자 화면이
연결되는 지점입니다.

## 전체 지도

```text
┌─ backend (uvicorn) ─────────────────────────────────────────┐
│ ServerError → CORS → RequestId → Exception → router         │
│   endpoint (def, 스레드풀)                                   │
│     ├ Depends: get_db / get_current_user                    │
│     ├ Pydantic 검증 (요청)                                   │
│     ├ Service ─ 소유권·중복·상태 검사, AppException           │
│     │    ├ Repository ─ SQLAlchemy → PostgreSQL             │
│     │    ├ Adapter Factory ─ mock / yfinance / OpenAI       │
│     │    └ LLMGateway ─ 라우팅·개인정보·캐시·예산·에스컬레이션  │
│     ├ enqueue_*_safe ─ Redis 큐                              │
│     └ success() → response_model → ApiResponse JSON          │
└──────────────────────────────────────────────────────────────┘
        │ Redis                              │ PostgreSQL
        ▼                                    ▼
┌─ worker (rq worker) ────────┐   ┌─ scheduler (rq cron) ─────┐
│ SessionLocal()              │   │ cron_config import 시 등록 │
│ JobRun(running)             │   │ registry의 enabled 스케줄  │
│ Service 재사용 (같은 코드)   │   │ → Redis 큐                │
│ 항목별 격리 + rollback       │   └───────────────────────────┘
│ JobRun(success/failed)      │
└─────────────────────────────┘
```

## 코드베이스 전체를 관통하는 원칙 10가지

1. **설정은 한 곳** — `Settings`가 유일한 출처. import 시점 검증으로 잘못된 설정은 기동을 막는다.
2. **경계에서만 예외 처리** — 외부 API·사용자 입력에서만 `except`. 내부는 흘려보내 미들웨어가
   공통 봉투로 변환한다.
3. **응답은 하나의 봉투** — `{data, message, error, meta}`. 성공·실패의 모양이 같다.
4. **계층은 단방향** — endpoint → service → repository → model. 아래가 위를 모른다.
5. **소유권은 service 첫 줄** — `_get_owned_*`가 없으면 데이터 유출.
6. **중복·경합은 두 겹** — service의 친절한 사전 검사 + DB 제약의 최종 보장.
7. **외부는 인터페이스 뒤로** — `base`/`mock`/`real` 삼각 구조. 외부 라이브러리 타입이 도메인에
   들어오지 않는다.
8. **판정에는 근거를** — `reason`·`evidence`를 함께 저장하고, 판단 시점 맥락은 스냅샷으로 복사한다.
9. **무거운 것은 워커로** — 실행 기록(`JobRun`)을 남기고, 항목 단위로 실패를 격리한다.
10. **민감 정보는 구간으로** — 클라우드로 나가는 값은 `CloudSafePayload` + 등급 문자열.

## 코드베이스의 성숙도 편차

이 투어에서 반복해 확인한 것은 **같은 문제의 해법이 도메인마다 다르다**는 점입니다.

| 문제 | 미흡한 곳 | 잘 된 곳 |
| --- | --- | --- |
| N+1 조회 | `WatchlistService`(04), `AssetService.lookup`(05) | `SignalService`(09), `news_insights.repository`(10) |
| 트랜잭션 경계 | repository 각자 커밋(03·04) | `flush()` + 잡이 커밋, `begin_nested()`(09) |
| 값 검증 | Pydantic만 | + `CheckConstraint`(10) |
| 시간 고정 | `datetime.now(UTC)` 직접 | `clock.utcnow()`(10) |
| 응답 문서화 | `ApiResponse[list[Any]]`(04) | `response_model` 구체 타입(대부분) |
| 예외 규칙 | `HTTPException` 사용(08 worker.py) | `AppException`(그 외 전부) |

**나중에 만들어진 도메인일수록 정제되어 있습니다.** 새 기능을 만들 때는 `news_insights`와
`alert_engine`을 본보기로, 오래된 도메인을 고칠 때는 위 표를 체크리스트로 쓰면 됩니다.

## 이 투어를 마친 뒤 할 수 있는 것

- 새 도메인 추가 — 04단계 `watchlists` 골격 복사 → `app/db/models.py` import 추가 →
  마이그레이션 → `api_router` 등록 → 테스트
- 새 외부 연동 — 06단계 `base`/`mock`/`real` 삼각 구조 + `factory` 분기 + `Settings` 플래그
- 새 LLM 기능 — 07단계 `LLMTaskType` 추가 → `router.py` 라우트 → `prompts/` 프롬프트 →
  `schema.py` 응답 모델 → `privacy.py` 스냅샷 변환
- 새 배치 — 08단계 잡 골격 복사 → `registry.py`에 cron 등록 → `enabled` 플래그
- 장애 대응 — `X-Request-ID`로 로그 추적, `Failed to fetch`면 500 로그부터, 데이터가 안 보이면
  `job_runs` 테이블 확인
