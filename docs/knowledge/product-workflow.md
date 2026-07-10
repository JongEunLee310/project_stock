# Product Workflow

이 문서는 `project_stock` 제품의 런타임 흐름을 설명한다. 개발/하네스 절차인
[workflow.md](workflow.md)와 별개로, 시스템이 실제로 데이터를 어떻게 처리하는지를
다룬다. 비즈니스 규칙은 [domain-knowledge.md](domain-knowledge.md), API 계약은
[../api/frontend-api-spec.md](../api/frontend-api-spec.md)를 기준으로 한다.

## 큰 그림

투자 리서치/감시 흐름은 세 갈래로 나뉜다.

- **데이터 수집 흐름**: 외부 provider에서 가격·뉴스 원시 데이터를 받아 원본 아카이브·검증을
  거쳐 정규화 테이블에 적재한다. 이후 분석 흐름과 (후속) LLM 입력의 재료가 된다.
- **백그라운드 분석 흐름**: 수집된 뉴스를 분석해 리포트와 Signal/Alert를 생성한다.
  RQ 워커 잡 또는 스케줄러가 트리거한다.
- **사용자 요청 흐름**: 사용자가 API로 포트폴리오 점검, 매수 전 체크, 알림/후보
  검토 등 판단 보조 기능을 직접 호출한다.

provider(`market`/`news`/`disclosure`/`portfolio`)는 모드별로 주입되며, 로컬·테스트 기본값은
deterministic mock이다. `market`은 `mock` / `yfinance`(일봉 실수집) / `real`을, `news`는
`mock` / `rss`(회사명 쿼리 실수집) / `real`을 지원하고, 나머지는 `mock` / `real`이다.

```mermaid
flowchart LR
    subgraph trigger["트리거"]
        SCHED["스케줄러<br/>(수집 잡 / analyze_all_watchlists_job)"]
        ADD["관심종목 추가<br/>(자동 분석 큐잉)"]
        WJOB["워커 잡 enqueue<br/>(news / analysis)"]
    end

    subgraph bg["백그라운드 분석 흐름"]
        PIPE["관심종목 분석 파이프라인"]
        SIG["Signal"]
        ALERT["Alert"]
        PIPE --> SIG --> ALERT
    end

    subgraph user["사용자 요청 흐름"]
        RESEARCH["종목 리서치 / 매수 체크리스트"]
        PORT["포트폴리오 집중도 점검"]
        REVIEW["알림 / 후보 검토"]
    end

    SCHED --> WJOB
    ADD --> WJOB
    WJOB --> PIPE
    ALERT --> REVIEW
    PORT --> SIG
    DATA[("리포트 / 시그널 / 알림")]
    bg --> DATA --> user
```

## 관심종목 분석 파이프라인

핵심 백그라운드 흐름이다. `analyze_watchlist_job`(RQ 잡)이 `WatchlistAnalysisService`를
실행하며, 관심목록의 각 종목을 순회한다. 종목 단위로 트랜잭션을 처리하고, 한 종목이
실패하면 롤백 후 `failures`에 기록하고 다음 종목으로 넘어간다.

관심종목 추가 API가 성공하면 해당 watchlist의 `analyze_watchlist_job`을 자동으로 큐에
적재한다. Redis 장애 등 큐잉 실패는 경고로 기록하되 관심종목 추가 응답에는 영향을 주지
않는다. 세션 밴드 스케줄은 `analyze_all_watchlists_job`을 적재해 모든 watchlist를
순차 분석하며, 수동 분석 API도 인증된 사용자가 같은 분석 잡을 큐에 적재하는 경로다.

종목별 처리 순서:

1. **뉴스 수집**: news adapter의 `fetch_query`에 회사명(`Asset.name`)과 대문자로 정규화한
   시장 값(`Asset.market.upper()`)을 전달해 원시 뉴스를 수집·저장하고, 이번 실행에서 새로
   저장된 뉴스만 News Item로 만든다.
2. **AI 요약**: 각 News Item을 LLM으로 요약한다.
3. **가설 충돌 분석**: 종목의 최신 투자 가설과 뉴스를 비교해 충돌 상태
   (`SUPPORTS` / `NEUTRAL` / `CONFLICTS`)와 무효화 조건 충족 여부(`invalidation_triggered`)를 판정한다.
4. **리서치 리포트 생성**: 요약·가설 충돌 결과를 담은 리포트를 만든다.
5. **룰 엔진 → 시그널**: 아래 규칙으로 Signal을 생성한다.
6. **알림 생성**: 생성된 Signal마다 사용자 Alert를 만든다. 중복 키(dedup key)가 이미
   있으면 새 Alert를 만들지 않는다.

집계 결과(`AnalysisFlowResult`)로 처리 종목 수와 생성된 news item / report / signal /
alert 수, 그리고 실패 목록을 반환한다.

```mermaid
flowchart TD
    START["관심목록 종목 순회"] --> NEWS["1 뉴스 수집<br/>News Item 생성"]
    NEWS --> SUMMARY["2 AI 요약"]
    SUMMARY --> CONFLICT["3 가설 충돌 분석<br/>SUPPORTS / NEUTRAL / CONFLICTS"]
    CONFLICT --> REPORT["4 리서치 리포트 생성"]
    REPORT --> RULES["5 룰 엔진"]
    RULES --> HASSIG{"시그널 생성?"}
    HASSIG -->|"yes"| SIGNAL["Signal 생성"]
    HASSIG -->|"no"| NEXT["다음 뉴스 / 종목"]
    SIGNAL --> DEDUP{"dedup key<br/>이미 존재?"}
    DEDUP -->|"no"| ALERT["Alert 생성"]
    DEDUP -->|"yes"| SKIP["Alert 생략"]
    ALERT --> NEXT
    SKIP --> NEXT

    FAIL["종목 처리 예외"] -.->|"롤백 후 failures 기록"| NEXT
```

> 종목 단위 트랜잭션이다. 한 종목이 실패하면 롤백하고 `failures`에 남긴 뒤 다음 종목으로 넘어간다.

### 룰 엔진 규칙

기본 규칙(`default_rules`)은 두 가지이며, News Item과 가설 충돌 결과를 입력으로 받는다.

- **High-impact 뉴스 규칙**: News Item의 영향도가 `HIGH` 또는 `CRITICAL`이면
  `RISK_ALERT` 시그널을 만든다(점수 `CRITICAL`=80, `HIGH`=60).
- **가설 충돌 규칙**: `invalidation_triggered`면 `THESIS_BROKEN`(risk `CRITICAL`, 점수 90),
  충돌 상태가 `CONFLICTS`면 `RISK_ALERT`(risk `HIGH`, 점수 70). 그 외에는 생성하지 않는다.

## 뉴스 수집 잡

`collect_news_job`(RQ 잡)은 회사명 쿼리로 원시 뉴스를 실수집한다. `NEWS_PROVIDER=rss`일 때
Google News 검색 RSS를 종목별 쿼리로 호출한다. 분석 파이프라인과 달리 요약·시그널 단계 없이
수집만 수행한다. 처리 순서:

1. **universe 산출**: 인자로 심볼을 주지 않으면 관심종목(watchlist) + 보유종목(portfolio)의
   `(symbol, market)` 합집합을 대상으로 삼고, 각 대상의 회사명(`assets.name`)을 함께 싣는다.
   심볼을 명시하면 assets에서 조회하고 미존재 심볼은 경고 후 건너뛴다.
2. **쿼리 수집**: 종목별로 회사명을 쿼리에 넣어 RSS를 호출한다. market별 locale을 부여해
   (KOSPI/KOSDAQ→`ko/KR`, NASDAQ/NYSE→`en-US/US`, 미지 market은 기본 locale + 경고로
   fail-open) 한국·미국 종목을 모두 커버한다.
3. **종목 태깅 저장**: per-company 쿼리라 반환 기사를 전부 대상 `(symbol, market)`에 귀속시켜
   `raw_news_events`에 저장한다. `url` unique 제약으로 동일 기사 재수집은 스킵한다(멀티종목
   기사는 first-writer-wins).

종목 단위 실패는 격리되어 다음 종목으로 넘어가고, 잡 전체는 JobRun으로 추적한다. 이 잡은
LLM을 호출하지 않는다 — 산출물은 `raw_news_events` 적재까지이며, 정규화(News Item)·요약·
시그널은 분석 파이프라인의 범위다. 두 잡 모두 JobRun으로 실행을 기록한다(아래).

## 가격 수집 잡

`collect_prices_job`(RQ 잡)은 일봉 가격을 실수집한다. `MARKET_PROVIDER=yfinance`일 때
yfinance 단일 provider가 시장 suffix(`.KS`/`.KQ`)로 미국·한국을 모두 커버한다. 처리 순서:

1. **universe 산출**: 인자로 심볼을 주지 않으면 관심종목(watchlist) + 보유종목(portfolio)의
   `(symbol, market)` 합집합을 대상으로 삼는다.
2. **수집**: provider로 일봉을 받는다. 미지 market은 fail-closed로 건너뛴다(경고).
3. **원본 아카이브**: 정규화 전 원본 payload를 `raw_prices`에 저장한다. `payload_hash`가
   이미 있으면 재저장하지 않는다(중복 스킵).
4. **검증**: 결측·미래 날짜 bar는 drop, 통화 불일치·이상치(전일 대비 수익률 절대값이 임계
   초과)는 경고하되 유지한다.
5. **적재**: 검증 통과분을 `prices`에 upsert한다. unique 제약(symbol·market·interval·
   timestamp)으로 중복을 흡수해 재수집이 멱등이다.

종목 단위 실패는 격리되어 다음 종목으로 넘어가고, 잡 전체는 JobRun으로 추적한다. 이 잡은
LLM을 호출하지 않는다 — 산출물은 `prices`·`raw_prices` 적재까지이며, Feature 계산·Context
조립·LLM 입력 패키징은 후속 범위다.

## 시그널 스냅샷 잡

`snapshot_signal_states_job`(RQ 잡)은 자산별 현재 dominant Signal을 하루 한 번
`asset_signal_snapshots`에 기록한다. dominant 판정은 `GET /api/v1/signals?view=current`와
같은 `SignalRepository.list_current_by_asset` 로직을 재사용하므로, `WATCHLIST_STATUS_PRIORITY`
우선순위와 score 정렬 규칙이 한 곳에서 유지된다.

스냅샷은 `(asset_id, snapshot_date)` unique 키로 멱등 upsert된다. 같은 날 잡을 다시 실행하면
행을 추가하지 않고 해당 일자의 `signal_id`·`signal_type`·`score`·`captured_at`를 갱신한다.
활성 dominant Signal이 없는 자산도 `signal_id=null`, `signal_type=null`, `score=null` 행으로
남긴다. 이 null 스냅샷 덕분에 시그널 만료처럼 새 Signal write가 없는 변화도 다음 실행에서
`CLEARED` 변화로 파생할 수 있다.

API 노출 계약:

- `GET /api/v1/signals?view=current`: 각 항목에 `change`를 포함한다. 스냅샷이 아직 없으면
  `change=null`이다. `view=all` 응답에는 이 필드를 추가하지 않는다.
- 모든 시그널 응답은 구조화 근거 불릿 `key_points: list[str]`를 포함하며, 저장값이
  `null`이면 빈 배열로 내려간다.
- `GET /api/v1/signals/changes`: 일별 스냅샷의 인접 diff 중 `UNCHANGED`가 아닌 항목을
  `snapshot_date`·`captured_at` 역순으로 반환한다. `limit`은 기본 20이고, `since`를 주면 해당
  일자 이후의 스냅샷 변화만 반환한다.
- `GET /api/v1/signals/summary?view=current`: 현재 dominant Signal을 `WATCH`·`RISK`·`BUY`·
  `RESEARCH` 4개 카테고리로 집계하고, 최신 스냅샷 일자와 직전 스냅샷 일자의 카테고리 count
  차이를 `delta_by_category`로 반환한다. 비교할 스냅샷 쌍이 없으면 delta는 모두 0이다.

## 스케줄러

스케줄러는 RQ 내장 cron으로 수집·분석 잡을 큐에 적재한다. 레지스트리에는
`price_collection`(`10 22 * * 1-5`)과 `news_collection`(`0 * * * *`) 외에
`analysis_kr_open`(`0 23 * * 0-4`), `analysis_kr_main`(`0 0-7 * * 1-5`),
`analysis_us_session`(`0 13-21 * * 1-5`), `analysis_kr_post`
(`0 9,11 * * 1-5`), `signal_snapshot`(`30 11 * * 1-5`)가 등록되어 있다.
분석 스케줄 4종은 기본값이 `False`인
`ANALYSIS_SCHEDULE_ENABLED` 플래그로 함께 제어하며, 비활성 상태에서는 레지스트리에
남지만 RQ cron에 등록되지 않는다. 이 플래그는 `app/scheduler/registry.py`를 임포트할 때
평가되므로 env 값을 변경한 뒤에는 스케줄러 프로세스를 재시작해야 한다. 스케줄러 프로세스는
`uv run rq cron app/scheduler/cron_config.py -u $REDIS_URL`로 실행한다.

로컬에서 `docker compose up`을 실행하면 default 큐를 소비하는 worker와 이 scheduler가
API·PostgreSQL·Redis와 함께 기동된다. worker에는 코드 자동 재시작이 적용되지 않으므로
코드 변경 뒤에는 worker 컨테이너를 재시작해야 한다.

compose에서 RQ 프로세스(worker·cron)를 띄울 때는 `sh -c 'exec rq ... -u "$REDIS_URL"'`
패턴을 표준으로 쓴다. `exec`로 셸을 RQ 프로세스로 치환해야 컨테이너 종료 시그널(SIGTERM)이
RQ에 직접 전달되어 처리 중인 잡의 warm shutdown이 동작하고, compose YAML에서는 `$`를
`$$`로 이스케이프해 변수 확장을 컨테이너 셸에 위임한다. 다른 기능에서 Redis 큐 프로세스를
추가할 때도 이 패턴을 따른다 (PR #246 Q1 논의).

수동 실행 경로(`POST /api/v1/worker/scheduler/jobs/{job_name}/run`)도 같은 RQ enqueue
경로를 사용하며, 응답의 `job_id`는 RQ job id다. 설계 배경은
[ADR-003](../decisions/ADR-003-scheduler-approach.md)을 참고한다.

## JobRun 생명주기

백그라운드 잡은 JobRun으로 추적된다.

- 시작 시 `running` 상태로 기록한다.
- 정상 종료 시 `success`로 갱신한다.
- 예외 발생 시 `failed`로 갱신하고 에러 메시지를 남긴다.
- 분석 잡은 종목별 부분 실패를 JobRun에 함께 기록한다.

```mermaid
stateDiagram-v2
    [*] --> running: start
    running --> success: 정상 종료
    running --> failed: 예외 (에러 메시지 기록)
    success --> [*]
    failed --> [*]
```

실행 기록은 `GET /api/v1/job-runs`로 조회한다. (RQ enqueue 응답의 `queued`는 큐 적재
상태이며 JobRun 상태와 별개다.)

## 사용자 요청 흐름

분석 파이프라인이 만든 데이터를 사용자가 API로 소비·판단하는 흐름이다.

- **종목 리서치**: 종목 기본 정보·시세(mock), 리서치 요약, 매수 전 체크리스트를 조회한다.
  체크리스트는 필수 4개 항목 체크와 memo 입력이 모두 충족되면 완료로 판정한다.
- **포트폴리오 집중도 점검**: 요약(섹터/현금 비중 포함)을 조회하고 점검을 실행한다.
  시세 기반 비중이 `concentration_threshold`를 초과한 종목에 대해 시그널을 만든다.
- **시그널 검토**: 화면에서 종목당 현재 dominant 시그널만 소비할 때는
  `GET /api/v1/signals?view=current`를 사용한다. 변화 표시는 스냅샷 기반 `change` projection을
  사용하고, 최근 변화 타임라인은 `GET /api/v1/signals/changes`, 카테고리 KPI와 전일대비 delta는
  `GET /api/v1/signals/summary?view=current`를 사용한다.
- **알림 검토**: Alert를 읽음/숨김 처리한다. 발송 전 Alert Candidate는 사람이 검토해
  읽음/확정한다(상태 전이 순서는 강제하지 않는다).
- **가설 관리**: 투자 가설을 생성·수정·비활성화한다. 분석 파이프라인은 종목의 최신
  활성 가설을 충돌 분석 입력으로 사용한다.

## 관련 문서

- [domain-knowledge.md](domain-knowledge.md): 비즈니스 규칙·도메인 용어·정책 결정.
- [llm-data-pipeline.md](llm-data-pipeline.md): 외부 데이터→정규화·검증·Feature·ContextBundle→LLM 파이프라인 전체 지침.
- [../api/frontend-api-spec.md](../api/frontend-api-spec.md): 화면별 API 매핑과 catalog.
- [../backend-v0.2.md](../backend-v0.2.md): 로컬 실행·provider 전환·API 호출 가이드.
- [../designs/019-watchlist-analysis-flow.md](../designs/019-watchlist-analysis-flow.md): 분석 플로우 설계.
- [../designs/020-rule-engine.md](../designs/020-rule-engine.md): 룰 엔진 설계.
- [../designs/065-price-ingestion-pipeline.md](../designs/065-price-ingestion-pipeline.md): 가격 실수집 파이프라인 설계.
- [../designs/066-news-ingestion-pipeline.md](../designs/066-news-ingestion-pipeline.md): 뉴스 실수집 파이프라인 설계.
