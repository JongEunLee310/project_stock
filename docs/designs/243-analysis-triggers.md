# Analysis Triggers — 설계 스켈레톤

## Status

Draft

## Background

분석 파이프라인(`analyze_watchlist_job` → `WatchlistAnalysisService.run`)은 구현되어 있으나
실행 주체가 없다. 스케줄러 레지스트리에는 수집 잡 2종(`price_collection`, `news_collection`)만
등록되어 있고, `POST /api/v1/worker/jobs/analysis`는 인증도 없어 FE 버튼 연동에 바로 사용할
수 없는 상태다. 이 설계는 이슈 #243의 트리거 3종을 추가해 관심종목 추가 → 시그널 생성까지의
체인을 완성한다.

파이프라인은 URL 기준 2중 중복 제거(`raw_news_events.url` unique 제약,
`AnalysisRepository.exists_by_url`)로 증분 실행되므로 트리거가 중복·고빈도로 발동해도 새
뉴스가 없으면 LLM 호출은 발생하지 않는다. (`app/worker/jobs/analysis.py:12-38` 참고)

## 변경 범위

### 트리거 1 — 관심종목 추가 시 자동 큐잉

종목이 `watchlists/{watchlist_id}/items`에 추가되면 해당 watchlist의 분석 잡을 큐에 적재한다.
큐잉 실패(Redis 다운 등)는 종목 추가 자체를 실패시키지 않는다. 이는 시스템 경계 에러 처리 원칙에
따른 것으로, Redis는 분석 파이프라인의 보조 인프라이지 종목 추가의 필수 조건이 아니기 때문이다.

변경 파일:
- `app/api/v1/endpoints/watchlists.py` — `add_watchlist_item` 핸들러에 큐잉 호출 추가
- `app/worker/jobs/analysis.py` — 새 헬퍼 함수 추가

새 함수 시그니처 (`app/worker/jobs/analysis.py`):

```
def enqueue_watchlist_analysis_safe(watchlist_id: int) -> None
```

책임: Redis 큐에 `analyze_watchlist_job`을 적재한다. `Exception` 발생 시 `logger.warning`으로
기록하고 예외를 억제한다. 호출자에게 실패를 전파하지 않는다.

`add_watchlist_item` 흐름:

1. `WatchlistService(db).add_item(watchlist_id, current_user.id, data)` 호출 (기존과 동일)
2. 성공 후 `enqueue_watchlist_analysis_safe(watchlist_id)` 호출
3. 큐잉 성공 여부와 무관하게 기존 응답(`ApiResponse[WatchlistItemResponse]`) 반환

### 트리거 2 — 스케줄러 레지스트리 등록

`analyze_watchlist_job(watchlist_id: int)`은 특정 watchlist 하나를 처리하므로 스케줄러에서
직접 등록할 수 없다. 모든 활성 watchlist를 순회하는 래퍼 잡을 신규 추가한다.

새 함수 시그니처 (`app/worker/jobs/analysis.py`):

```
def analyze_all_watchlists_job() -> None
```

책임: DB에서 모든 watchlist id를 조회한 뒤 각 id에 대해 `WatchlistAnalysisService.run(watchlist_id)`을
순차 실행한다. 잡 전체를 단일 JobRun으로 추적하며, watchlist 단위 실패는 `failures`에 기록하고
다음 watchlist로 진행한다(`analyze_watchlist_job`의 처리 방식과 동일).

레지스트리 등록 (`app/scheduler/registry.py`):

세션 밴드별로 `ScheduleDefinition`을 추가한다. `enabled` 값은
`settings.ANALYSIS_SCHEDULE_ENABLED`에서 읽는다.

#### UTC 변환 표 (KST = UTC+9, 요일 경계 이동 포함)

| 밴드 | KST 현지 시각 (거래소 기준) | UTC cron 표현식 | 발화 횟수/일 | 등록 이름 |
|------|--------------------------|----------------|-------------|----------|
| KR 사전~정규 — 첫 회 | 평일 08:00 | `0 23 * * 0-4` | 5회/주 | `analysis_kr_open` |
| KR 사전~정규 — 나머지 | 평일 09:00–16:00 매시 | `0 0-7 * * 1-5` | 8회/일 | `analysis_kr_main` |
| US 세션 | 평일 22:00–다음날 06:00 매시 | `0 13-21 * * 1-5` | 9회/일 | `analysis_us_session` |
| KR 마감 후 평가 | 평일 18:00, 20:00 | `0 9,11 * * 1-5` | 2회/일 | `analysis_kr_post` |

**요일 경계 근거 (KR 밴드 08:00):**
KST 월 08:00 − 9h = UTC 일 23:00. KST 기준 월~금의 08:00는 UTC 기준 일~목의 23:00이 되어
요일이 하루 앞으로 당겨진다. 나머지 시각(09:00–16:00)은 UTC 기준 같은 요일(월~금)에 해당하므로
분리해 등록한다.

**US 세션 요일 경계 없음:**
KST 평일 22:00를 UTC로 변환하면 같은 날 13:00이 되고, 다음날 06:00은 전날 21:00이 된다.
따라서 KST 기준 자정을 넘어도 UTC 기준 요일 경계는 발생하지 않는다 — `0 13-21 * * 1-5`로
단일 표현식으로 충분하다.

**검산:**
- `0 23 * * 0-4`: UTC 일(0)~목(4) 23:00 → KST 월~금 08:00 ✓
- `0 0-7 * * 1-5`: UTC 월~금 00:00–07:00 → KST 월~금 09:00–16:00 ✓
- `0 13-21 * * 1-5`: UTC 월~금 13:00–21:00 → KST 월~금 22:00–다음날 06:00 ✓
- `0 9,11 * * 1-5`: UTC 월~금 09:00, 11:00 → KST 월~금 18:00, 20:00 ✓

기존 전례: `price_collection` cron `10 22 * * 1-5`는 UTC 기준이며 이 설계도 동일 관례를 따른다.
(출처: `app/scheduler/registry.py:30`)

#### dev/demo 프로필 분리

`Settings`에 플래그를 추가한다 (`app/core/config.py`):

```
ANALYSIS_SCHEDULE_ENABLED: bool = False
```

기본값 `False`로 dev에서는 분석 스케줄이 비활성화된다. 데모·배포 환경에서는
`ANALYSIS_SCHEDULE_ENABLED=true`를 env로 주입해 활성화한다. cron 문자열 자체의 env
오버라이드는 이 단계에서 하지 않는다(과설계).

### 트리거 3 — 수동 트리거 정비

`POST /api/v1/worker/jobs/analysis`에 인증과 rate limit을 추가한다.

**인증 근거:** 같은 파일의 `enqueue_llm_analysis_job`은 `get_current_user`를 사용하는 반면
(`worker.py:88`), `enqueue_analysis_job`과 `enqueue_news_job`은 인증이 없다. 이번 범위에서
`enqueue_analysis_job`에만 인증을 추가한다. `enqueue_news_job`과 `run_scheduler_job_once`는
내부 운영 용도로 현재 인증 없이 노출되어 있으며 이번 범위에서 변경하지 않는다.
(출처: `app/api/v1/endpoints/worker.py:64,76,88,108`)

**rate limit 방식:** Redis TTL 기반 단순 제한. 새 인프라를 도입하지 않는다.

- Redis 키 스킴: `rate_limit:analysis_manual:{user_id}` (가정 — 기존 키 스킴 레퍼런스 없음,
  구현 전 `KEYS rate_limit:*` 또는 소스 검색으로 확인 필요)
- TTL: 60초 (이슈 #243 "분당 1회" 명세. 출처: 이슈 #243 요구사항 3)
- 초과 시: HTTP 429 + `ErrorCode.RATE_LIMIT_EXCEEDED` + `Retry-After: 60` 헤더

변경 파일:
- `app/api/v1/endpoints/worker.py` — `enqueue_analysis_job`에 `current_user: User = Depends(get_current_user)` 추가, rate limit 검사 추가
- `app/core/error_codes.py` — `RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"` 추가

## 계약 확정

### Settings 신규 필드

| 필드 | 타입 | 기본값 | env 키 |
|------|------|--------|--------|
| `ANALYSIS_SCHEDULE_ENABLED` | `bool` | `False` | `ANALYSIS_SCHEDULE_ENABLED` |

### 함수 시그니처 요약

| 모듈 | 함수 | 책임 |
|------|------|------|
| `app/worker/jobs/analysis.py` | `enqueue_watchlist_analysis_safe(watchlist_id: int) -> None` | 큐 적재, 실패 억제·로그 |
| `app/worker/jobs/analysis.py` | `analyze_all_watchlists_job() -> None` | 전체 watchlist 순차 분석, JobRun 추적 |

### ErrorCode 신규 추가

`app/core/error_codes.py`에 `RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"` 추가.
기존 패턴과 동일한 `str` enum 형식. (출처: `app/core/error_codes.py:4-33` 패턴)

### rate_limit Redis 키 스킴

`rate_limit:analysis_manual:{user_id}` — value는 임의, TTL 60초. SET NX+EX 원자 연산으로
적재. 키가 존재하면 429 반환. (가정: 기존 rate_limit 키 레퍼런스 없음 — 구현 전 codebase
검색으로 확인)

## 범위 밖

- FE 동기화 버튼 연동 (FE repo 별도 이슈)
- `enqueue_news_job`, `run_scheduler_job_once` 인증 추가 (현재 범위 아님)
- 시장별(KR/US) universe 분리 실행 — 증분 구조라 현 단계 불필요
- 주말 회차 스케줄 (후속)
- cron 문자열 env 오버라이드 (과설계)
- 분석 파이프라인 내부 로직 변경

## 관련

- 이슈 #243
- `app/scheduler/registry.py`, `app/scheduler/cron_config.py` — 기존 스케줄 등록 패턴
- `app/api/v1/endpoints/worker.py` — 기존 worker 엔드포인트
- `docs/knowledge/product-workflow.md` — 구현 후 스케줄러·분석 파이프라인 섹션 갱신 필요
- `docs/decisions/ADR-003-scheduler-approach.md` — 스케줄러 설계 배경
