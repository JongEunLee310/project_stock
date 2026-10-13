# Codex Handoff Task

## Source Issue

#472 — [BE] RAG 2차-2: EDGAR 10-K 사업·위험요인 섹션 수집 (트래킹 #445, 에픽 #438)

## Task Summary

관심종목 중 미국 종목의 최근 10-K 2건에서 Item 1(Business)과 Item 1A(Risk Factors)를 추출해
`knowledge_documents`(#471)에 저장한다. 공시 어댑터, 수집 서비스, job, 주간 스케줄, 수동 스크립트를 만든다.

## Goal

- `FILING_PROVIDER=real`, `SEC_USER_AGENT` 설정 시 미국 관심종목마다 최근 10-K 2건 × 섹션 2개가 저장된다.
- 이미 저장한 공시 섹션(같은 `external_id`)은 다시 받지 않는다.
- 종목 하나의 실패가 다른 종목을 막지 않는다. 국내 종목은 `unsupported`로 기록하고 건너뛴다(DART는 #473).
- 저장된 문서는 기존 매시 임베딩 job이 `KNOWLEDGE` 청크로 적재한다(#471에서 연결됨).

## Background

- 설계 정본: `docs/designs/445-filing-knowledge-collection.md` §1·§3·§5·§6·§7. **반드시 먼저 읽는다.** 특히 §3.3
  섹션 추출 규칙은 실제 10-K 5건으로 확인한 것이므로 그대로 구현한다(줄 시작 제목만 인정, 가장 긴 구간 선택).
- 지식 정본: `app/domains/knowledge/`(`KnowledgeDocumentRepository`, `KnowledgeDocumentCreate`, `KnowledgeKind`,
  `FilingSection`)
- 어댑터·factory 패턴: `app/adapters/disclosure/`, `app/adapters/factory.py`(`get_news_adapter` 등), 설정
  `app/core/config.py`·`.env.example`
- job·스케줄 패턴: `app/worker/jobs/agents.py`(`JobRunService`, `partial_failures`), `app/scheduler/registry.py`,
  수동 스크립트 `scripts/run_daily_research.py`
- 관심종목 대상: `WatchlistItemRepository.list_watched_asset_ids()`, 자산 `AssetRepository`
- 시장 값: 미국 `NASDAQ`·`NYSE`, 국내 `KOSPI`·`KOSDAQ`(`app/domains/prices/validator.py`)
- HTTP는 기존 의존성 `httpx`를 쓴다. 의존성 추가는 없다. `uv add`, `uv sync`, 네트워크, `git fetch`, docker
  명령을 하지 않는다. 테스트는 네트워크 없이 `httpx.MockTransport` 등으로 작성한다.

## Implementation Scope

1. **어댑터**(`app/adapters/filings/`) — 설계 §3.1
   - `base.py`: `FilingRef`, `FilingSectionText`, `FilingProvider`(ABC), `FilingFetchError`
   - `edgar.py`: `EdgarFilingProvider(user_agent, client: httpx.Client | None = None, min_interval_seconds=0.2)`
     - 티커와 CIK 매핑(`company_tickers.json`, 인스턴스 안에서 1회 로드 후 캐시), 제출 목록에서 `form == "10-K"`만
       최신 순으로 `limit`건, 본문 URL 조립(설계 §1 표)
     - 모든 요청에 `User-Agent` 헤더, 요청 간 최소 간격
     - 섹션 추출은 순수 함수(`extract_10k_sections(html_text) -> list[FilingSectionText]`)로 분리해 단위 테스트한다.
       규칙은 설계 §3.3(블록 경계 줄바꿈, 줄 시작 제목, 대소문자·공백 무시, `.`/`:` 허용, 가장 긴 구간, 500자 미만
       누락, 20만 자 상한과 잘림 표시)
     - 네트워크 오류, HTTP 오류, JSON 형식 오류, 매핑에 없는 티커는 `FilingFetchError`
   - `mock.py`: `MockFilingProvider`(결정적 값)
   - factory `get_filing_provider(market: str) -> FilingProvider | None`: `FILING_PROVIDER=mock`이면 mock, `real`이면
     미국 시장은 EDGAR(`SEC_USER_AGENT`가 없으면 None과 경고 로그), 그 밖의 시장은 None
2. **설정**: `FILING_PROVIDER: Literal["mock", "real"] = "mock"`, `SEC_USER_AGENT: str | None = None`(+`.env.example`)
3. **수집 서비스**(`app/domains/knowledge/filing_service.py`) — 설계 §3.2
   - `FilingCollectionService(db, provider_factory=get_filing_provider).collect(asset_ids=None) -> FilingCollectionResult`
   - 결과: `saved`, `skipped_existing`, `missing_sections`, `failed`, `unsupported`
   - `external_id`는 `edgar:{accession}:{section}`(section은 `BUSINESS`·`RISK_FACTORS`). `title`은
     "{회사명} 10-K FY{연도} — Item 1. Business" 형식(회사명은 asset 이름, 연도는 `report_date` 연도),
     `source_name="SEC EDGAR"`, `license_note`는 설계 §2.1 예시, `effective_date=filed_date`,
     `metadata_`는 설계 §2.1 공시 항목(`form`, `cik`, `accession`, `report_date`, `fiscal_year`, `section`,
     잘렸으면 `truncated`)
   - 이미 있는 공시는 본문을 받지 않도록, 보고서의 두 섹션 `external_id`가 모두 있으면 `fetch_sections`를 호출하지 않는다.
   - 종목 단위 commit, 예외 시 rollback 후 `failed` 기록
4. **job·스케줄·스크립트** — 설계 §5
   - `collect_filings_job(asset_ids=None)`(`app/worker/jobs/filings.py`), 실행 기록 `filing_collection`,
     부분 실패 metadata
   - 스케줄 `filing_collection`, cron `0 1 * * 6`, `enabled=True`(mock 기본값이면 mock 데이터만 쌓이지 않도록
     `FILING_PROVIDER=mock`일 때 job이 수집을 건너뛰고 로그만 남기는 방식을 검토해 보고한다. 기존 다른 수집 job이
     mock에서 어떻게 동작하는지 확인해 같은 정책을 따른다)
   - `scripts/collect_filings.py --asset-id N`(반복 가능), 결과 JSON 출력
5. 설계 문서는 구현과 다르게 정한 것이 있을 때만 고친다.

## Out of Scope

- DART(#473), 10-Q·8-K·정정 공시, 재무제표 수치
- 검색·Q&A·에이전트 변경, 인덱서 변경
- 실제 네트워크 호출 테스트(로컬 실측은 orchestrator가 리뷰 단계에서 한다)

## Protected Files

없음.

## Test Requirements

- 섹션 추출(합성 HTML 픽스처, `tests/fixtures/filings/` 등):
  - 목차와 본문에 같은 제목이 있을 때 본문을 고름
  - 문단 안의 상호 참조 `Refer to “Item 1A. Risk Factors”`에서 잘리지 않음
  - 대문자·붙여 쓴 제목 `ITEM 1A.RISK FACTORS`, `\xa0` 공백, `Item 1A:` 형식
  - 500자 미만 누락, 20만 자 초과 잘림과 표시
- EDGAR 어댑터(`httpx.MockTransport`): CIK 10자리 패딩, 10-K만 최신 순 `limit`건, 본문 URL, `User-Agent` 헤더,
  HTTP 오류·매핑 없음 → `FilingFetchError`
- factory: mock / real+미국 / real+UA 없음 / real+국내
- 수집 서비스: 신규 저장 필드, 중복 시 `fetch_sections` 미호출, 섹션 누락 기록, 종목 실패 격리, 국내 종목 `unsupported`
- job: 성공·부분 실패·예외 기록, 스케줄 등록(cron)

## Verification Commands

```
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## ADR Need

불필요(ADR-018이 공시 수집 출처와 정본을 정함).

## Failure Record Need

불필요.

## Risk Level

Medium — 외부 API 연동(공개·무인증). 요청 간격과 `User-Agent`로 SEC 정책을 지킨다.

## Expected Output

- 현재 브랜치 `feat/472-edgar-filing-collection`에서 작업한다. 새 브랜치를 만들지 않는다.
- 커밋이 샌드박스에서 막히면 미커밋 상태로 두고 보고한다. push와 PR 생성은 하지 않는다.
- 최종 보고: 변경 파일 목록, mock 정책 결정과 근거, 가정, 검증 결과

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.

## Addendum (2026-10-13, orchestrator 실측 후)

### 배경

- 실제 EDGAR로 미국 3종목 10-K 2건씩 섹션 12건(약 55만 자)을 수집했고, 실제 Ollama `bge-m3`로 임베딩하니
  537개 청크에 17분 18초가 걸렸다(`embed_documents` 1회 실행).
- RQ 2.9.1의 기본 job timeout은 180초다(`rq.Queue.DEFAULT_TIMEOUT`). `app/scheduler/cron_config.py`는
  `rq_cron.register(func, "default", cron=...)`로 timeout 없이 등록하므로, 워커에서 이 job은 180초에 강제 종료되고
  트랜잭션이 롤백돼 공시 청크가 영원히 적재되지 않는다. 실 DB에서 `embed_documents` 최장 실행은 이미 2분 39초다.
- `rq_cron.register`는 `job_timeout` 인자를 받는다(시그니처 확인).

### 추가 범위

1. `ScheduleDefinition`에 `job_timeout: int | None = None`을 추가하고 `cron_config._register_cron_jobs`와
   `ManualSchedulerRunner.run`이 이 값을 넘기게 한다(`SchedulerQueue.enqueue` 프로토콜도 맞춘다).
2. 값: `embed_documents` 1800초, `daily_research_agent` 3600초, `filing_collection` 900초. 나머지는 None(기본값 유지).
   값은 `app/worker/jobs/` 또는 registry에 상수로 두고 출처(이 실측)를 주석 한 줄로 남긴다.
3. API에서 직접 enqueue하는 일일 리서치(`app/api/v1/endpoints/worker.py`의 `run_daily_research_job`,
   `app/worker/jobs/agents.py`의 `enqueue_daily_research_safe`)도 같은 3600초 상수로 `job_timeout`을 지정한다.
4. 설계 `docs/designs/445-filing-knowledge-collection.md` §4에 실측(537청크 17분)과 timeout 결정을, 설계
   `docs/designs/459-daily-research-agent.md` §6에 일일 리서치 job timeout을 한 줄씩 반영한다.

### 추가 테스트

- cron 등록 시 timeout 전달(`rq_cron.register` monkeypatch), 수동 실행 시 timeout 전달, 세 스케줄의 값
- 일일 리서치 enqueue 두 곳의 `job_timeout`
