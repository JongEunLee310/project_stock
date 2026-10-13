# BE 설계: RAG 2차 — 지식 정본과 기업 공시 섹션 수집 — #445

상태: **설계 초안(Draft)** — 2026-10-13. 하위 이슈 #471(지식 정본), #472(EDGAR), #473(DART).
#445의 다중 풀 검색과 인용 종류 구분은 #474로 분리했다. 배치·저장 결정은 ADR-018(BE 내부 pgvector,
`knowledge_documents` 정본)을 따른다.

이 문서는 지식 정본 모델, 공시 수집 어댑터, 섹션 추출 규칙, 임베딩 적재, 실행 경로를 스켈레톤
수준으로 확정한다. 구현 코드와 쿼리는 담지 않는다. 출처가 없는 경계값은 "가정"으로 표기했다.

## 사용자 결정(2026-10-13)

| 항목 | 결정 |
|---|---|
| 범위 | 공시 수집만 먼저 한다(에이전트 2 #464의 선행). 다중 풀 검색과 인용 구분은 #474로 분리 |
| 순서 | EDGAR 10-K를 먼저 하고, DART 사업보고서는 API 키를 발급받은 뒤 이어서 한다 |

## 1. 코드·외부 사실

| 사실 | 출처 | 설계 영향 |
|---|---|---|
| 청크 테이블은 `source_type`·`source_id`로 정본을 가리킨다 | `app/domains/rag/model.py` | `KNOWLEDGE` + `knowledge_documents.id` |
| `ChunkSourceType`은 `NEWS`만 있다 | `app/domains/rag/types.py` | `KNOWLEDGE` 추가 |
| 인덱서는 `raw_news_events`를 id 순으로 스캔하고, `content_hash`가 같으면 건너뛴다 | `app/domains/rag/indexing_service.py` | 지식 문서도 같은 방식으로 스캔 |
| Q&A와 일일 리서치 검색은 `source_types=(NEWS,)`로 필터한다 | `app/domains/rag/service.py:86-93`, `app/domains/agents/daily_research/service.py:385-392` | 지식 청크가 들어와도 기존 검색 결과는 바뀌지 않음 |
| 시장 값 `NASDAQ`·`NYSE`(미국), `KOSPI`·`KOSDAQ`(국내) | `app/domains/prices/validator.py:14-19` | 시장으로 EDGAR·DART 분기 |
| 기존 `DisclosureProvider`는 제목·URL 수준의 공시 목록이다 | `app/adapters/disclosure/base.py` | 본문 섹션 수집은 별도 어댑터로 둠 |
| EDGAR 티커와 CIK 매핑 `https://www.sec.gov/files/company_tickers.json` | 2026-10-13 실측(AAPL 320193, NVDA 1045810, GOOGL 1652044) | 매핑 출처 |
| 제출 목록 `https://data.sec.gov/submissions/CIK{10자리}.json`의 `filings.recent`(`form`, `accessionNumber`, `filingDate`, `reportDate`, `primaryDocument`) | 2026-10-13 실측 | 10-K 선택 |
| 본문 URL `https://www.sec.gov/Archives/edgar/data/{cik}/{accession 하이픈 제거}/{primaryDocument}` | 2026-10-13 실측(AAPL 2025 10-K) | 원문 링크 |
| SEC는 요청마다 연락처가 담긴 `User-Agent`를 요구하고, 초당 10건을 넘지 않게 요구한다 | SEC EDGAR fair access 정책 | `SEC_USER_AGENT`, 요청 간격 |
| 10-K 본문에는 목차의 `Item 1.`·`Item 1A.`가 먼저 나오고, 본문 제목은 뒤에 다시 나온다. AAPL 2025 기준 목차 항목 간 거리는 수십 자, 본문 Item 1은 약 1.6만 자, Item 1A는 약 6.8만 자 | 2026-10-13 실측 | §3.3 추출 규칙 |

## 2. 데이터 모델(#471)

### 2.1 `knowledge_documents`(`app/domains/knowledge/model.py`)

| 필드 | 타입 | 제약 | 설명 |
|---|---|---|---|
| `id` | int | PK | |
| `kind` | str(30) | not null | `KnowledgeKind`. 이번에는 `FILING_SECTION`만 |
| `title` | str(500) | not null | 예: "Apple Inc. 10-K FY2025 — Item 1A. Risk Factors" |
| `content` | text | not null | 정리한 본문(줄바꿈 유지) |
| `asset_id` | int | FK `assets.id`, nullable | 종목 문서면 값이 있음(용어집 등은 null) |
| `source_name` | str(100) | not null | `SEC EDGAR`, `DART` |
| `source_url` | str(1000) | not null | 원문 링크 |
| `license_note` | str(255) | nullable | 예: "U.S. government public filing" |
| `effective_date` | date | nullable | 공시는 제출일(`filingDate`) |
| `external_id` | str(200) | not null | 공시는 `{source}:{접수번호}:{섹션키}` |
| `content_hash` | str(64) | not null | `content`의 sha256 |
| `metadata` | JSON | not null, 기본 `{}` | 공시: `form`, `cik`/`corp_code`, `accession`, `report_date`, `fiscal_year`, `section` |
| `created_at`·`updated_at` | timestamptz | `TimestampMixin` | |

- unique: (`kind`, `external_id`)
- 인덱스: (`asset_id`, `kind`, `effective_date`)
- 같은 `external_id`가 이미 있으면 다시 쓰지 않는다. 공시 원문은 제출 후 바뀌지 않는다는 전제다(정정
  공시는 별도 접수번호 `10-K/A`이며 이번 범위 밖).
- Python 속성 이름은 `metadata_`로 둔다(SQLAlchemy 예약어 회피, `JobRun.metadata_`와 같은 방식).

### 2.2 enum

| enum | 위치 | 값 |
|---|---|---|
| `KnowledgeKind` | `app/domains/knowledge/types.py` | `FILING_SECTION` |
| `FilingSection` | 같은 파일 | `BUSINESS`, `RISK_FACTORS` |
| `ChunkSourceType` | `app/domains/rag/types.py` | `NEWS`, `KNOWLEDGE`(추가) |

### 2.3 repository(`app/domains/knowledge/repository.py`)

| 함수 | 책임 |
|---|---|
| `get_by_external_id(kind, external_id) -> KnowledgeDocument \| None` | 중복 수집 확인 |
| `add(data) -> KnowledgeDocument` | 저장(commit은 호출자) |
| `list_after_id(after_id, limit) -> list[KnowledgeDocument]` | 인덱서 스캔 |
| `list_by_asset(asset_id, kind, limit) -> list[KnowledgeDocument]` | 에이전트 2가 최근 보고서 두 건을 읽는 용도 |

## 3. 공시 수집(#472 EDGAR, #473 DART)

### 3.1 어댑터(`app/adapters/filings/`)

| 타입·함수 | 책임 |
|---|---|
| `FilingRef`(값 객체) | `source`, `company_id`(CIK·corp_code), `accession`, `form`, `filed_date`, `report_date`, `document_url` |
| `FilingSectionText`(값 객체) | `section: FilingSection`, `heading`, `text` |
| `FilingProvider.list_annual_reports(symbol, limit) -> list[FilingRef]` | 최근 연간보고서 목록(최신 순) |
| `FilingProvider.fetch_sections(ref) -> list[FilingSectionText]` | 본문에서 섹션 추출. 못 찾은 섹션은 빠짐 |
| `EdgarFilingProvider` | 티커와 CIK 매핑(프로세스 안 캐시), 제출 목록에서 `form == "10-K"`만, 본문 HTML 섹션 추출 |
| `MockFilingProvider` | 테스트·기본값 |
| `DartFilingProvider`(#473) | corp_code 매핑, 사업보고서 목록, 원문 문서 섹션 추출 |
| factory `get_filing_provider(market) -> FilingProvider \| None` | 미국 시장이면 EDGAR, 국내면 DART(키 없으면 None), 설정이 mock이면 mock |

설정(`app/core/config.py`, `.env.example`)

| 키 | 기본값 | 설명 |
|---|---|---|
| `FILING_PROVIDER` | `mock` | `mock` 또는 `real` |
| `SEC_USER_AGENT` | 없음 | `real`이면서 값이 없으면 EDGAR 수집을 건너뛰고 경고 |
| `DART_API_KEY` | 없음 | #473 |

- HTTP는 기존 의존성 `httpx`를 쓴다(`pyproject.toml`). 요청 간격은 0.2초(가정, 초당 5건)다.
- 네트워크 오류와 HTTP 오류는 어댑터 경계에서 `FilingFetchError`로 바꾼다.

### 3.2 수집 서비스(`app/domains/knowledge/filing_service.py`)

`FilingCollectionService.collect(asset_ids: list[int] | None = None) -> FilingCollectionResult`

- 대상은 관심종목 전체(`list_watched_asset_ids`)이거나 지정한 종목이다.
- 종목마다 최근 연간보고서 2건(가정. 에이전트 2가 직전 보고서와 비교하려면 2건이 필요하다)을 확인하고,
  섹션마다 `external_id`가 없으면 저장한다.
- 결과에는 `saved`, `skipped_existing`, `missing_sections`(종목 → 못 찾은 섹션), `failed`(종목 → 사유),
  `unsupported`(지원하지 않는 시장 또는 키 없음)를 담는다.
- 종목 하나의 실패가 다른 종목을 막지 않는다. 종목 단위로 commit한다.

### 3.3 EDGAR 섹션 추출 규칙

- HTML을 텍스트로 바꿀 때 블록 요소(`p`, `div`, `tr`, `li`, `br`, `h1`~`h6`, `table`) 경계를 줄바꿈으로 남기고,
  줄마다 공백(`\xa0` 포함)을 하나로 줄인 뒤 빈 줄을 버린다.
- 제목은 **줄 시작**에 오는 `Item 1.`(Business), `Item 1A.`(Risk Factors), 다음 경계 `Item 1B.`·`Item 1C.`·`Item 2.`
  만 인정한다. 대소문자를 무시하고, `Item`과 번호 사이·번호와 구두점 뒤 공백은 없어도 된다(GOOGL은
  `ITEM 1A.RISK FACTORS`). 구두점은 `.`과 `:`를 허용한다.
- 문단 안의 상호 참조(NVDA의 `Refer to "Item 1A. Risk Factors"`)는 줄 시작이 아니라서 제목으로 보지 않는다.
  줄 시작 조건 없이 찾으면 NVDA Item 1이 상호 참조에서 잘린다(2026-10-13 실측).
- 같은 제목이 여러 번 나오면(목차와 본문) 시작 후보마다 다른 번호의 다음 제목까지 길이를 재서 가장 긴
  구간을 고른다. 목차 구간은 수십 자라 자연히 탈락한다.
- 실측 결과(2026-10-13, 줄 시작 규칙): AAPL FY2025 Item 1 약 1.6만 자·1A 약 6.8만 자, NVDA FY2026 4.8만·11.5만,
  NVDA FY2025 5.5만·11.1만, GOOGL FY2025 2.4만·8.5만, GOOGL FY2024 3.1만·8.3만. 모두 본문 제목에서 시작해
  다음 Item 제목 직전에서 끝났다.
- 쪽 머리말·꼬리말(`Table of Contents`, `Apple Inc. | 2025 Form 10-K | 4` 등)이 본문에 섞이는 것은 허용한다.
- 섹션 길이가 500자(가정) 미만이면 못 찾은 것으로 본다.
- 본문 저장 상한은 섹션당 20만 자(가정)이고, 넘으면 잘라 내고 `metadata.truncated=true`를 남긴다.

### 3.4 DART(#473)

착수할 때 실제 보고서로 확인한다(OQ2). 사업보고서는 「II. 사업의 내용」을 `BUSINESS`로 본다. 국내
보고서에는 10-K의 Item 1A에 해당하는 독립 장이 없는 경우가 많아, 어떤 절을 `RISK_FACTORS`로 볼지 정해야 한다.

## 4. 임베딩 적재(#471)

- `EmbeddingIndexer.run`이 뉴스 스캔 뒤에 지식 문서를 같은 방식으로 스캔한다. `max_documents`는 두 원천을
  합한 상한이고, 둘 중 하나라도 남으면 `has_more=True`다.
- 지식 문서 청크: `source_type=KNOWLEDGE`, `source_id=knowledge_documents.id`, `content_quality=FULL`,
  `asset_ids=[asset_id]`(없으면 빈 배열), `published_at=effective_date`의 KST 자정(가정), 임베딩 입력은
  `title` + 빈 줄 + `content`, 청킹은 기존 `chunk_text`(1,500자, 겹침 150자)다.
- 10-K 한 건의 두 섹션은 약 60~110개 청크다(§3.3 실측 길이 기준). 미국 관심종목 3개 × 2건이면 첫 적재에
  약 500개 청크이고, 이후에는 새 보고서가 들어올 때만 늘어난다.
- 2026-10-13 실측에서 실제 공시 537청크의 `bge-m3` 임베딩은 17분 18초가 걸렸으므로,
  `embed_documents`의 job timeout은 1800초, `filing_collection`은 900초로 지정한다.
- 뉴스 인덱싱의 순서와 결과는 바뀌지 않는다.

## 5. 실행 경로(#472)

| 경로 | 내용 |
|---|---|
| job | `collect_filings_job(asset_ids: list[int] \| None = None)`(`app/worker/jobs/filings.py`), `JobRunService`로 `filing_collection` 기록, 부분 실패는 metadata `partial_failures` |
| 스케줄 | `filing_collection`, 매주 토요일 01:00 UTC(가정) |
| 수동 스크립트 | `scripts/collect_filings.py --asset-id N` |

- #445 초안은 "분기 job"이었다. 그러나 제출 목록 확인은 종목당 요청 한 번이라 싸고, 에이전트 2가 새 보고서를
  빨리 받으려면 주간 확인이 낫다. 이미 받은 공시는 다시 받지 않으므로 주간 실행 비용은 목록 확인뿐이다.
- 임베딩은 기존 매시 임베딩 job이 처리한다. 수집 job은 임베딩을 직접 호출하지 않는다.

## 6. 경계

- 공시는 공개 자료(PUBLIC)라 클라우드 LLM 입력에 넣을 수 있다(ADR-009). 마스킹 대상이 아니다.
- 저장하는 것은 섹션 본문과 메타데이터뿐이다. 재무제표 수치는 이번 범위 밖이다(실적은 기존
  `earnings` 도메인).
- `knowledge_documents`는 에이전트와 Q&A가 함께 읽는 정본이다. 에이전트 2는 이 테이블을 읽기만 한다.

## 7. 테스트 전략

- 모델·마이그레이션: unique 제약, `metadata` 기본값, 단일 head
- 인덱서: 지식 문서 청크 필드, 내용이 같으면 건너뜀, 바뀌면 재적재, 뉴스 결과 불변, `has_more`
- EDGAR 어댑터: 실제 10-K에서 잘라 낸 HTML 픽스처(목차와 본문을 모두 포함)로 섹션 추출, 매핑 실패, HTTP 오류를
  `FilingFetchError`로 변환, `User-Agent` 헤더 포함. 네트워크는 쓰지 않는다.
- 수집 서비스: 신규 저장, 중복 건너뜀, 섹션 누락 기록, 종목 실패 격리, 지원하지 않는 시장
- 로컬 실측(리뷰 단계): 실제 EDGAR로 관심종목 미국 종목의 섹션을 수집하고 임베딩까지 확인

## 8. Open Questions

| # | 질문 | 처리 |
|---|---|---|
| OQ1 | 10-K 서식이 회사마다 달라 추출 규칙이 일부 회사에서 실패할 수 있다 | #472 실측에서 관심종목 전체로 확인. 실패는 `missing_sections`로 기록 |
| OQ2 | DART 사업보고서에서 `RISK_FACTORS`로 볼 절 | #473 착수 시 실제 보고서로 결정 |
| OQ3 | 섹션 길이와 청크 수가 커서 검색 결과를 공시가 독점할 수 있다 | #474(다중 풀 검색)에서 풀별 상위 k로 해결. 그전까지 기존 검색은 `NEWS`만 본다 |

## 9. 범위 밖

- 다중 풀 검색, 인용 종류 구분(#474)
- 10-Q, 8-K, 정정 공시, 재무제표 수치
- 공시 비교 분석(에이전트 2, #464)
- FE 표시
