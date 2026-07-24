# BE 설계: 뉴스 인텔리전스 파이프라인 1 — 수집(source_documents 적재) — 이슈 #397

상태: **설계 확정** — 2026-07-24. 트래킹 #391의 1단계, 에픽 #307 후속. 선행 계약·모델은
`docs/designs/307-news-intelligence.md`.

이 문서는 이미 쌓인 원천 데이터를 `news_insights.source_documents`로 적재하는 경로의 범위와
매핑 규칙을 스켈레톤 수준으로 확정한다. 실제 쿼리·정규화 로직은 담지 않는다.

## 배경

`news_insights` 도메인의 어느 테이블에도 애플리케이션에서 행을 쓰는 코드가 없다. 유일한 기록
경로는 `seed.py`뿐이라 화면은 시드 1건 또는 빈 상태만 보여준다(#391).

반면 원천은 이미 존재한다.

- `raw_news_events`(약 2,622건, `app/domains/raw_news/`) — 어댑터가 수집한 **원본**.
  `RawNewsService.collect_and_save`로 적재된다. `url`이 unique이고 `body`·`payload`를 가진다.
- `news_items`(약 2,481건, `app/domains/news/`) — 원본을 `normalizer`가 정제한 **파생 뷰**.
  `raw_news_event_id`로 원본을 참조하고 `asset_id`로 종목에 묶인다.

수집 단계는 이 원천을 `source_documents`로 잇는 것부터 시작한다.

## 1. 정본 선택 — `raw_news_events`

`source_documents`의 정본은 `raw_news_events`로 한다.

| 후보 | 판정 | 근거 |
|---|---|---|
| `raw_news_events` | **정본** | 원본·최다. `body`(본문)·`url`(unique) 보유. 문서 1건 = 행 1건 |
| `news_items` | 제외 | `asset_id`별로 쪼갠 파생 뷰라 문서 1건이 여러 행으로 중복될 수 있어 "문서" 단위와 어긋난다 |

`source_documents`는 문서 단위 테이블이다(`content_hash` unique). 종목 정제 결과인 `news_items`를
정본으로 쓰면 같은 문서가 종목 수만큼 중복 적재된다.

## 2. 수집 범위 — 이번 단계는 `NEWS`

`DocumentType`은 여섯 종(`NEWS`·`DISCLOSURE`·`EARNINGS`·`ANALYST_REPORT`·`COMMUNITY`·
`COMPANY_IR`)이나, 이번 단계는 `raw_news_events`가 담고 있는 `NEWS`만 적재한다.

공시(`DISCLOSURE`)는 현재 `DisclosureProvider.fetch()`로 실시간 조회만 하고 **저장 테이블이
없다.** 공시 원천을 `source_documents`로 적재하려면 공급원 저장 경로 확보가 선행이며, 이는
5단계(#401 수급·일정) 또는 별도 후속에서 다룬다. 화면 문구에 맞추려고 저장되지 않는 문서
유형을 지어내지 않는다.

## 3. 필드 매핑

`raw_news_events` → `source_documents` 매핑이다.

| source_documents | 원천 | 비고 |
|---|---|---|
| `document_type` | `NEWS` 고정 | §2 |
| `source_name` | `raw.source` | 현재 값은 실매체명이 아닌 Google News 피드 제목 — §4.6, 정규화는 후속 #403 |
| `source_url` | `raw.url` | |
| `external_id` | `raw.id`(문자열화) | nullable. 재적재 추적용 |
| `title` | `raw.title` | |
| `raw_content` | `raw.body` | **NOT NULL 충돌** — §4.1 |
| `normalized_content` | 비움(`null`) | 정규화는 추출 단계(#398) 책임 |
| `language` | 기본값 | **원천에 없음** — §4.2 |
| `published_at` | `raw.published_at` | **NOT NULL 충돌** — §4.3 |
| `collected_at` | `raw.collected_at` | |
| `content_hash` | 파생 계산 | **원천에 없음, 멱등 키** — §4.4 |
| `source_reliability` | 기본값 | **원천에 없음, 0~1 필수** — §4.5 |
| `processing_status` | `PENDING` | 추출 대기 상태 |

## 4. NOT NULL 충돌·부재 필드 처리

`source_documents`의 필수 필드 중 원천이 채우지 못하는 것들의 처리 규칙이다. **값을 지어내지
않는다**는 원칙과 NOT NULL 제약이 부딪히는 지점이라 규칙을 명시한다.

### 4.1 `raw_content` ← `raw.body` (body nullable)

`raw_content`는 NOT NULL이나 `raw.body`는 nullable이다. `body`가 없는 원천은 본문 없는 문서이므로
**적재 대상에서 제외**한다. `title`로 `raw_content`를 대체하면 본문이 있는 것처럼 보이게 되어
추출 단계(#398)를 오도한다. 제외한 건수는 적재 결과에 보고한다.

### 4.2 `language` (원천에 없음)

원천에 언어 필드가 없다. 이번 단계는 판별기를 도입하지 않고 기본값 `"ko"`로 둔다. 국내 뉴스
수집이라는 현재 원천의 성격에 따른 것이며, 다국어 원천이 생기면 판별을 별도로 다룬다.

### 4.3 `published_at` ← `raw.published_at` (nullable)

`published_at`은 NOT NULL이나 원천은 nullable이다. 원천 발행 시각이 없으면 `collected_at`으로
대체한다. 대체 여부를 데이터에 표식으로 남기지는 않으나(스키마에 자리 없음), 발행 시각 부재는
드문 경우이고 수집 시각이 발행 시각의 합리적 상한이다.

### 4.4 `content_hash` (멱등 키)

`content_hash`는 unique·NOT NULL이며 재적재를 막는 멱등 키다. 원천에 없으므로 파생 계산한다.
`news_items`에도 `content_hash` 컬럼이 있으나 정의만 있고 실제로 채우는 코드가 없어(seed의 mock
값 외 대입 0건) **재사용할 산식이 없다.** 따라서 이 단계에서 산식을 새로 정의한다 — 정규화된
`source_url`+`title`의 SHA-256 hex(64자, `String(64)`와 일치). URL 정규화는 이미 있는
`app/domains/news/normalizer.py`의 `canonicalize_url`을 재사용해 쿼리스트링·fragment 차이로 같은
문서를 다른 문서로 세지 않게 한다.

### 4.5 `source_reliability` (0~1 필수, 원천에 없음)

`source_reliability`는 NOT NULL이고 0~1 범위 제약이 있으나 원천에 없다. **출처 신뢰도를 지금
지어내지 않는다.** 신뢰도 평가 규칙(출처별 가중치 등)이 정의된 적이 없다.

**전건 중립값 `0.5`(미평가)로 적재한다(2026-07-24 확정).** 신뢰도 티어링은 실제 매체명이 있어야
성립하는데, 아래 §4.6대로 현재 원천에는 매체명이 없다. 매체 정규화와 티어링은 후속 #403에서
다루며, 그때 이 값이 실질 신뢰도로 채워진다. `0.5`는 "미평가"를 뜻한다.

### 4.6 `source_name` — 현재 값은 실매체명이 아님

수집원은 Google News 검색 RSS이고 어댑터는 `source`에 `parsed_feed.feed.title`을 넣는다. 이
값은 실매체명이 아니라 검색어 기반 피드 제목(`"쿼리 - Google 뉴스"` 형태)이다. 실매체명은
`raw.payload`(`dict(entry)`)의 `entry.source.title`·`entry.title` 접미사에 있다.

이번 단계는 `source_name`을 `raw.source` 그대로 적재한다(단순 적재). `payload`에서 실매체명을
추출해 정규화하고 그 위에 신뢰도 티어링을 얹는 작업은 후속 **#403**이다. #403은 착수 전
`payload` 구조를 실데이터 표본으로 검증한다.

## 5. 적재 경로 — 함수 골격

신규 모듈 `app/domains/news_insights/ingestion.py`(파일명 확정은 구현 재량).

| 함수 | 시그니처(개략) | 책임 |
|---|---|---|
| `ingest_source_documents` | `(session) -> IngestionResult` | 원천 조회 → 매핑 → 멱등 적재를 조율 |
| `_map_raw_to_source_document` | `(RawNewsEvent) -> SourceDocument \| None` | 단건 매핑. body 없으면 `None`(§4.1) |
| `IngestionResult`(projection) | — | 적재·스킵·중복 건수 집계 보고 |

- 멱등: 이미 존재하는 `content_hash`는 재적재하지 않는다. 재실행이 안전해야 한다.
- 값 생성 금지: §4의 규칙 밖에서 원천에 없는 값을 만들지 않는다.
- 파생 뷰(projection)의 타입 이름은 `DTO`를 쓰지 않는다(ADR-009 계열 관례).

## 6. 실행 트리거

이번 단계는 적재 **경로**를 만드는 데 집중한다. 스케줄러·주기 실행은 6단계(#402 처리 현황)
및 데이터 수집 파이프라인 마일스톤(#5)과 함께 다룬다. 이번 단계의 실행은 수동 진입점(관리
명령 또는 테스트)으로 충분하며, 진입점 형태는 구현 재량으로 둔다.

## 7. 결정 현황 — 전부 확정(2026-07-24)

- **공시(`DISCLOSURE`) 이번 범위 제외.** 저장 경로가 없어 이번 단계는 `NEWS`만 적재한다. 공시
  저장 경로는 별도 후속에서 다룬다.
- **`source_name`·`source_reliability` 단순 적재(방향 A).** `source_name`은 원천 값 그대로,
  `source_reliability`는 전건 중립 `0.5`(미평가). 실매체명 추출·정규화와 신뢰도 티어링은 후속
  **#403**으로 분리했다(§4.5·§4.6). 이로써 수집 착수의 블로커가 모두 해소됐다.

## 8. ADR·실패 기록 판단

- ADR: 기존 고정 계약·모델에 데이터를 채우는 작업이고 스키마 변경이 없으므로 **불요**. 정본
  선택·매핑 규칙은 이 설계 문서가 근거로 충분하다.
- 실패 기록: 해당 없음. 실패한 접근을 대체하는 것이 아니라 부재하던 생산 경로를 만드는
  작업이다.
