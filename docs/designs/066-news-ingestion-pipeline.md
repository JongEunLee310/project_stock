# 066 · 실데이터 뉴스 수집 파이프라인 (News Ingestion Pipeline)

Status: Draft
작성: Claude Code (orchestrator)
관련: BE #170(구현 이슈), Milestone 데이터 수집 파이프라인 — 백엔드(#5). 가격 실수집
설계 065의 후속 수집 슬라이스. LLM 하이브리드 아키텍처(Epic #141)의 데이터 선행.

## 1. 배경

가격에 이어 뉴스도 LLM 앞단에 넘길 실데이터가 필요하다. 현재 뉴스 수집 경로는 어중간한
상태다. RSS 실 어댑터(`app/adapters/news/rss.py`, feedparser 기반)가 이미 구현돼 있으나
**factory에 배선되지 않은 고아 상태**다. `get_news_adapter()`는 `mock`만 반환하고 `real`은
`NotImplementedError`를 던진다. 그래서 `collect_news_job`은 실제로는 mock 뉴스만 저장한다.

또한 매칭이 취약하다. `RSSNewsAdapter`는 심볼 문자열이 제목/요약에 포함되는지로 필터하는데,
미국 티커는 노이즈가 크고 **한국 종목은 심볼이 숫자 코드(`005930`)라 뉴스 본문에 등장하지
않아 사실상 0건**이다. 원본 테이블 `raw_news_events`에는 종목 연결 컬럼이 없어 독립 수집 시
어느 종목의 뉴스인지도 유실된다.

본 설계는 뉴스의 첫 실수집 수직 슬라이스로 **RSS 뉴스 실수집 + 회사명 기반 매칭 + 종목
연결**만 다룬다. 정규화(`news_items`)와 LLM 요약은 기존 분석 파이프라인에 그대로 두고
건드리지 않는다. 가격의 `raw_prices` 원본 아카이브·`PriceIngestionService`·universe·job
선례를 미러한다.

## 2. 범위

포함:

- `RSSNewsAdapter`를 factory에 실배선(`NEWS_PROVIDER=rss`) + 설정.
- 회사명 쿼리 기반 per-company RSS 수집(설계 §4). 미국·한국 모두 커버.
- `raw_news_events`에 `symbol`·`market` 컬럼 추가(nullable) + 마이그레이션 → 종목 연결.
- `NewsIngestionService`: universe 대상별 수집 → `(symbol, market)` 태깅 → 원본 저장,
  대상 단위 격리(`PriceIngestionService` 미러).
- news universe resolver: 관심종목(watchlist) + 보유종목(portfolio) → `(symbol, market, name)`.
- `collect_news_job(symbols=None)`: None이면 universe 사용(하위호환 유지), `JobRun` 추적.
- 테스트: 쿼리 URL 생성·매칭·태깅, 원본 dedup, universe 해석, job 흐름.

비포함(후속 분리):

- 정규화(`raw_news_events` → `news_items`)와 LLM 요약 분리 — 기존 분석 파이프라인 유지.
- 공시(disclosure)·실적 실수집.
- 뉴스 스케줄 실등록(크론). 본 슬라이스는 수동/on-demand 실행으로 검증한다.
- 멀티종목 기사 다중 귀속(현재 `url` unique로 first-writer-wins, 한계로 기록).
- 감성/영향도 분류, 중복 기사 클러스터링, rate-limit·재시도 고도화.
- LLM 호출·판단(데이터는 LLM 흐름에 관여하지 않는다 — LLM은 마지막 칸).

## 3. 데이터 흐름

```
universe(watchlist + portfolio) → (symbol, market, name) 목록
  → 대상별 쿼리 RSS URL 생성(§4)
  → RSSNewsAdapter.fetch_query(name, market)   # per-company 피드 파싱
  → 엔트리에 (symbol, market) 태깅
  → RawNewsService.save_with_symbol(...)        # url unique dedup
  → JobRun succeed / fail
```

산출물은 `raw_news_events` 적재까지다. 정규화·요약은 기존 분석 파이프라인이 담당하며 본
파이프라인은 LLM을 호출하지 않는다.

## 4. 회사명 쿼리 매칭

정적 피드 substring 필터는 커버리지가 설정 피드에 갇혀 한국 종목을 못 채운다. 대신 종목마다
회사명 쿼리 RSS URL을 템플릿으로 만들어 per-company 피드를 받는다. 반환 엔트리는 전부 그
종목에 귀속하므로 `(symbol, market)` 태깅이 확실하다.

| asset.market | locale(hl/gl) | 비고 |
| --- | --- | --- |
| KOSPI / KOSDAQ | `ko` / `KR` | 한국 |
| NASDAQ / NYSE | `en-US` / `US` | 미국 |
| (미지) | 기본 locale + 경고 | fail-open(수집은 시도, 경고 로깅) |

쿼리 URL은 설정 템플릿(예: 공개 뉴스검색 RSS 엔드포인트, API 키 불필요)에 `query=name`과
locale을 채워 만든다. 소스는 템플릿 설정으로 교체 가능하다. 네트워크·파싱 오류는 대상 단위로
격리한다.

## 5. 컴포넌트

### 5.1 `raw_news_events` 스키마 변경 — `app/domains/raw_news/`

model `RawNewsEvent`에 컬럼 추가:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| symbol | str \| None | 귀속 종목 심볼(nullable) |
| market | str \| None | 귀속 시장(nullable) |

dedup은 기존 `url` unique 제약을 유지한다. 멀티종목 기사는 first-writer-wins(먼저 저장된
종목에 귀속, 한계). 기존 분석 파이프라인 경로는 symbol/market을 채우지 않으므로 null로 저장돼
동작 불변이다. **DB 스키마 변경 → 마이그레이션 필요(설계 039 구조 준수).**

### 5.2 `RSSNewsAdapter` — `app/adapters/news/rss.py`

기존 `fetch(symbols)`(분석·mock 호환)는 유지하고, 쿼리 기반 수집 메서드를 추가한다.

```
class NewsAdapter(ABC):
    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]   # 기존
    def fetch_query(self, query: str, market: str) -> list[NewsAdapterResult]   # 신규
```

`RSSNewsAdapter.fetch_query` 책임: (1) `query`(회사명)와 `market` locale로 쿼리 RSS URL을
생성(템플릿 주입), (2) 해당 피드를 파싱, (3) 엔트리를 `NewsAdapterResult`로 변환해 필터 없이
반환. `MockNewsAdapter`도 `fetch_query`를 구현한다(질의별 합성 결과).

### 5.3 factory 분기 + 설정

- `app/adapters/factory.py`: `get_news_adapter()`에 `NEWS_PROVIDER == "rss"` 분기 추가
  (쿼리 템플릿을 주입해 `RSSNewsAdapter` 생성). 기존 `mock` 분기·`real` 미구현은 유지.
- `config`: `NEWS_PROVIDER` Literal에 `"rss"` 추가(기본 `mock` 유지). 쿼리 URL 템플릿 설정
  추가(기본값 제공, 소스 교체 가능). 실수집은 명시적 설정으로만 켠다.

### 5.4 `RawNewsService` 확장 — `app/domains/raw_news/service.py`

기존 `collect_and_save(adapter, symbols)`(분석 파이프라인 사용)는 유지한다. `(symbol, market)`을
받아 단일 결과를 저장하는 경로를 추가한다.

```
class RawNewsService:
    def save_with_symbol(self, result: NewsAdapterResult,
                         symbol: str, market: str) -> RawNewsEvent | None
```

`url` 중복이면 스킵(`None` 반환). `RawNewsEventCreate` 스키마에 `symbol`·`market`(optional)을
추가한다.

### 5.5 `NewsIngestionService`(신규) — `app/domains/raw_news/ingestion_service.py`

`PriceIngestionService`를 미러한다.

```
class NewsIngestionService:
    def __init__(self, db: Session) -> None
    def collect_and_save(self, adapter: NewsAdapter,
                         targets: list[tuple[str, str, str]]) -> IngestionResult
```

`collect_and_save` 책임(대상별): `adapter.fetch_query(name, market)` → 엔트리에 `(symbol,
market)` 태깅 → `RawNewsService.save_with_symbol` → 저장/스킵 카운트. 대상 단위 실패는 건너뛰고
계속하며, 수집/저장/스킵/실패 카운트를 `IngestionResult`로 집계해 반환한다.

### 5.6 news universe resolver — `app/domains/raw_news/universe.py`(신규)

`PriceUniverseResolver`를 미러하되 `name`까지 포함한다.

```
class NewsUniverseResolver:
    def resolve(self, symbols: list[str] | None = None) -> list[tuple[str, str, str]]
```

`symbols=None`이면 watchlist item + portfolio position의 asset을 합쳐 중복 제거한
`(symbol, market, name)` 목록을 산출한다. `symbols`가 주어지면 assets에서 해당 심볼의
`(market, name)`을 조회해 구성하고, 미존재 심볼은 건너뛴다(경고). 빈 목록이면 job은 no-op 성공.

### 5.7 worker job — `app/worker/jobs/news.py`

```
def collect_news_job(symbols: list[str] | None = None) -> None
```

기존 시그니처를 `| None = None`으로 확장(호출부 하위호환 유지). `JobRunService.start` →
`NewsUniverseResolver(db).resolve(symbols)` → `NewsIngestionService.collect_and_save(
get_news_adapter(), targets)` → succeed/fail. 기존 `RawNewsService.collect_and_save` 직접 호출은
새 흐름으로 교체한다.

## 6. 의존성

- `feedparser` — 이미 선언(추가 없음).
- `app/adapters/news/base.py`(`NewsAdapter`·`NewsAdapterResult`) — `fetch_query` 추가.
- `app/adapters/news/rss.py`·`mock.py` — `fetch_query` 구현.
- `app/adapters/factory.py` — `rss` 분기 추가.
- `app/core/config.py` — `NEWS_PROVIDER` Literal 확장 + 쿼리 템플릿 설정.
- `app/domains/raw_news/*` — model 컬럼 추가, schema/service 확장, ingestion_service·universe 신규.
- `app/domains/watchlists`·`app/domains/portfolios`·`app/domains/assets` repository — universe 재사용.
- `app/domains/jobs`(`JobRunService`) — 실행 추적 재사용.
- `app/worker/jobs/news.py` — 수집 흐름 교체.
- 마이그레이션 — `raw_news_events`에 `symbol`·`market` 컬럼 추가.

## 7. 테스트

- **쿼리 매칭**: 고정 fixture(RSS 응답 형태)로 `fetch_query`가 엔트리를 `NewsAdapterResult`로
  변환(네트워크 미접속). market별 locale 반영 단언.
- **태깅·저장**: `NewsIngestionService`가 대상별 엔트리에 `(symbol, market)`을 태깅해 저장,
  `url` 중복은 스킵, 대상 단위 실패 시 다음 대상 계속·카운트 단언.
- **universe resolver**: `symbols=None`이면 watchlist+portfolio 합집합·중복 제거·name 포함,
  명시 심볼은 assets 조회로 구성·미존재 스킵, 빈 universe no-op.
- **job**: `collect_news_job`이 `JobRun`을 start→succeed로 남기고, 대상 단위 실패 시에도 전체
  job이 실패로 끝나지 않음(정책상 성공 처리) 단언. 기존 mock 경로·시그니처 하위호환 단언.
- 기존 분석 파이프라인 경로(`RawNewsService.collect_and_save`) 회귀 없음.
- CI 3종(ruff+mypy+pytest) 통과.

## 8. 비범위 / 후속

- **정규화·요약 분리**: `raw_news_events` → `news_items` 정규화를 분석 파이프라인에서 분리해
  독립 수집 산출물로 승격(다음 슬라이스 후보).
- **공시(disclosure) 실수집**: DART/SEC 공시 provider 실연동.
- **뉴스 스케줄 실등록**: 주기 크론(설계 044 스케줄러 스켈레톤 활용).
- **매칭 고도화**: 멀티종목 다중 귀속, 중복 기사 클러스터링, 관련도 스코어링.
- **수집 정책 고도화**: rate-limit·재시도·소스 신뢰도 등급(정책 확정 시 ADR).

## ADR 판단

불필요. 기존 provider/factory 패턴과 가격 수집(설계 065) 선례를 따르는 데이터 적재이며 신규
아키텍처 결정이 없다. 소스 신뢰도 등급·자동 차단·스케줄 주기 확정 등 정책 도입 시 별도 ADR로
다룬다.
