# 069 · LLM 데이터 파이프라인 3단계 — News Normalizer 수집 잡 연결

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), 구현 이슈 BE #181,
Milestone 데이터 수집 파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(6.3 Normalization Layer·3단계·§7 레이어 매핑). 선행 2단계 설계 `docs/designs/068-raw-processing-status.md`.

## 1. 배경

가격 파이프라인은 `prices/ingestion_service.py`가 raw 저장 직후 정규화·검증까지 인라인으로
수행해 수집 잡과 완결 연결돼 있다. 반면 뉴스는 `collect_news_job` → `NewsIngestionService`가
`raw_news_events` 저장까지만 한다. 내부 표준 모델(`NewsItem`)로의 정규화는 현재 분석 도메인
`analysis/service.py._create_new_items`에 묶여 있고, 어댑터를 재조회(`_RecordingNewsAdapter`)하는
구조라 raw 저장과 분리돼 있다. (이 문단은 작성 시점 기준 서술이다 — `_RecordingNewsAdapter`는
PR #249에서 제거됐고, 분석 파이프라인 수집은 `fetch_query` 기반으로 정렬됐다. `NewsItem` 정규화가
분석 도메인에 묶여 있다는 문제의식 자체는 여전히 유효하다.)

지침 §7은 "뉴스 정규화를 `domains/news/`로 끌어와 수집 잡과 연결"하는 것을 3단계 과제로 명시한다.
지침 6.3은 Normalizer의 책임으로 외부 필드명 → 내부 필드명 변환, 날짜·시간대 정규화, 심볼 표기
통일, URL canonicalization을 든다. 본 단계는 명시적 `NewsNormalizer`를 신설해 뉴스 수집 잡 경로에
배선하고, 정규화 성공 시 2단계에서 만든 `processing_status`를 `normalized`로 전이시킨다(2단계
Decision F가 정의한 첫 writer). 검증(`failed` 전이·`DataQualityStatus`)은 4단계 몫이다.

## 2. 범위

포함:

- `NewsNormalizer`(`app/domains/news/normalizer.py`) 신설 — symbol·market·URL·`published_at`
  시간대 canonicalization + `RawNewsEvent` → `NewsItemCreate` 매핑(순수·무상태).
- 뉴스 정규화 서비스 경로 — raw 이벤트를 받아 asset 해소·URL dedup 후 `NewsItem` 생성, raw 행
  `processing_status='normalized'` 세팅.
- 뉴스 수집 잡 인라인 배선 — `NewsIngestionService`가 raw 저장 직후 정규화를 호출(가격 인라인
  패턴 대칭).
- `PriceNormalizer`(`app/domains/prices/normalizer.py`) 명시화 — 기존 인라인 canonicalization
  (symbol/market upper, timestamp UTC 변환) 추출, behavior-preserving.
- 정규화·canonicalization 회귀 테스트.

비포함(후속 단계):

- 뉴스 검증·`DataQualityStatus`·`ValidationErrorReason`·`failed` 세팅 — 4단계.
- 분석 플로우 `analysis/service.py._create_new_items` 수렴 리팩터 — 본 단계 미변경(Decision K).
- 기존 fetched `raw_news_events` 소급 정규화 배치 잡 — v0.1 미포함(수집 시점 정규화만).
- Feature·ContextBuilder·Gateway, route 노출, LLM 요약(summary/sentiment는 후속 분석 단계가 채움).

## 3. 컴포넌트 설계

### 3.1 NewsNormalizer (신규)

`app/domains/news/normalizer.py`. 순수·무상태 컴포넌트. DB·세션에 의존하지 않는다.

| 함수 | 시그니처 | 책임 |
| --- | --- | --- |
| canonicalize_symbol | `(symbol: str) -> str` | 제공자 접미사·접두사 제거 후 대문자화(예: `AAPL.O`, `NASDAQ:AAPL` → `AAPL`) |
| canonicalize_market | `(market: str) -> str` | 대문자·trim 통일(거래소 코드 형태 유지, Decision I) |
| canonicalize_url | `(url: str) -> str` | fragment·trailing slash 제거, host 소문자화(dedup 안정화) |
| normalize_published_at | `(value: datetime \| None) -> datetime \| None` | tz-naive 입력을 UTC로 보정(가격 `_as_utc` 관례 재사용) |
| to_news_item_create | `(event: RawNewsEvent, asset_id: int) -> NewsItemCreate` | 위 canonicalization을 적용해 raw 이벤트를 `NewsItemCreate`로 매핑 |

- summary·sentiment·impact_level 등 LLM 파생 필드는 채우지 않는다(후속 분석 단계가 담당).
- `NewsItemCreate.raw_news_event_id`는 원본 이벤트 id로 세팅해 역추적을 남긴다.

### 3.2 News 정규화 서비스 경로

`domains/news/`에 정규화 서비스 메서드를 둔다(신규 `NewsNormalizationService` 또는 기존
서비스 확장). 책임:

| 함수 | 시그니처 | 책임 |
| --- | --- | --- |
| normalize_event | `(event: RawNewsEvent) -> NewsItem \| None` | asset 해소·URL dedup 후 `NewsItem` 생성, 성공 시 raw 행 `processing_status='normalized'` |

- asset 해소: `AssetRepository.get_by_symbol_market(canonical_symbol, canonical_market)`.
- URL dedup: `NewsItemRepository.exists_by_url`로 기존 `NewsItem` 중복 회피.
- asset 미해소(symbol/market 부재 또는 매칭 asset 없음) 시 `NewsItem`을 만들지 않고 raw 행을
  `fetched`로 남긴다(Decision J).
- raw 행 상태 전이: `RawNewsEventRepository`에 `mark_normalized(event_id)` 류 메서드를 추가한다.

### 3.3 수집 잡 배선

`NewsIngestionService._collect_target`이 `save_with_symbol` 성공(비-None) 직후 `normalize_event`를
호출한다. `IngestionResult`에 `normalized_count`를 더한다. 가격 인라인 정규화 구조와 대칭.

### 3.4 PriceNormalizer 명시화

`app/domains/prices/normalizer.py`. 기존 `prices/ingestion_service.py`의 인라인
canonicalization(`normalized_symbol = symbol.upper()`, `normalized_market = market.upper()`,
`_as_utc`)을 명시적 컴포넌트로 추출한다.

| 함수 | 시그니처 | 책임 |
| --- | --- | --- |
| canonicalize_symbol | `(symbol: str) -> str` | 대문자화 |
| canonicalize_market | `(market: str) -> str` | 대문자화 |
| normalize_timestamp | `(value: datetime) -> datetime` | tz-naive → UTC 보정(기존 `_as_utc`) |

- behavior-preserving. `ingestion_service.py`가 이 컴포넌트를 사용하도록 위임만 바꾼다.
- 가격 검증(`_validate_bars`)은 4단계 정합 대상이며 본 단계에서 이동·변경하지 않는다.

## 4. Decisions

- **H. Normalizer는 순수·무상태 컴포넌트**: canonicalization 로직은 DB·세션 의존 없이 입력→출력만
  다룬다. asset 해소·`NewsItem` 저장·상태 전이 같은 부수효과는 서비스 경로에 둔다. 순수 부분을
  분리해 단위 테스트를 외부 API·DB 없이 돌린다(지침 12절).
- **I. market canonicalization은 대문자·trim까지**: 지침 6.3 예시(`NASDAQ:AAPL → AAPL / US`)의
  국가코드 축약(US/KR)은 v0.1에서 하지 않는다. `assets` 테이블이 market을 거래소 코드
  (`NASDAQ`/`KOSPI` 등)로 저장하고 `NewsItem.asset_id` 해소가 `(symbol, market)` 매칭에
  의존하므로, 국가코드로 접으면 asset 해소가 깨진다. 거래소 코드 형태를 유지하고 대문자·trim만
  한다. 국가코드 축약은 asset 키 정책이 정리되는 후속 단계에서 재검토한다.
- **J. asset 미해소 시 정규화하지 않고 fetched 유지**: `NewsItem.asset_id`는 not-null FK다.
  raw 이벤트의 symbol/market이 없거나 매칭 asset이 없으면 `NewsItem`을 만들 수 없다. 이 경우
  `NewsItem` 생성을 건너뛰고 raw 행을 `fetched`로 남겨(경고 로그) 후속 재처리 여지를 둔다.
  `failed`로 표시하지 않는다(`failed`는 4단계 검증 실패 의미). 수집 잡 경로는 targets가 asset·
  watchlist에서 유래하므로 대개 해소되지만, 방어적으로 이 분기를 둔다.
- **K. 분석 플로우는 이번 단계 미변경(divergence 인지)**: `analysis/service.py._create_new_items`도
  `NewsItem`을 생성한다. 본 단계는 이를 리팩터하지 않는다(Scope B). 두 경로 모두 `exists_by_url`로
  멱등하나, 수집 잡이 먼저 `NewsItem`을 만들면 분석 플로우가 해당 URL을 건너뛰어 요약·리포트
  대상에서 빠지는 행동 변화가 있을 수 있다. v0.1에서는 수용하고, 두 경로 수렴은 ContextBuilder가
  정규화 산출물을 소비하는 6단계 또는 별도 후속에서 처리한다. 분석 도메인은 protected로 둔다.

## 5. 마이그레이션

없음. `NewsItem`·`raw_news_events` 스키마는 그대로다(2단계에서 `processing_status` 컬럼 추가 완료).
본 단계는 컬럼 값을 쓰는 로직만 더하므로 신규 alembic revision이 필요 없다. 단일 head
`c3d4e5f60058`를 유지한다.

## 6. 테스트

- News raw payload(`RawNewsEvent`)를 `NewsItem`으로 정규화할 수 있다(asset 해소·필드 매핑, 지침
  12절).
- canonicalization 단위 테스트: symbol 접미사 제거·대문자, market 대문자, URL fragment·trailing
  slash 제거, `published_at` tz-naive → UTC.
- 뉴스 수집 잡 경유 시 raw 저장 + `NewsItem` 생성 + raw 행 `processing_status='normalized'` 전이
  회귀.
- asset 미해소 raw 이벤트는 `NewsItem`을 만들지 않고 `fetched`로 남는다(Decision J).
- URL 중복 시 `NewsItem`을 중복 생성하지 않는다(멱등).
- `PriceNormalizer` 추출 후 기존 가격 수집·정규화 테스트가 그대로 통과한다(behavior-preserving).
- CI 3종(ruff + mypy + pytest) 통과.

## 7. ADR 판단

불필요. 지침 §7이 정의한 3단계 배선을 기존 도메인 관례(가격 인라인 정규화 패턴) 안에서 구현하는
연장선이며, 새 아키텍처 결정을 도입하지 않는다. Decision I(거래소 코드 유지)·J(미해소 fetched
유지)·K(분석 divergence)는 설계 리뷰에서 이견이 있으면 조정하되 ADR 승격 대상은 아니다.
