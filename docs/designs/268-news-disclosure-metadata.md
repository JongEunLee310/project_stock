# Design — Issue #268: 뉴스·공시 분리 및 메타데이터 계약

FE 리서치 상세의 "뉴스 및 공시 요약" 카드가 뉴스와 공시를 분리해서 표시하고,
항목별로 분류·출처·게시 시각·중요도·영향·원문 링크와 AI 요약을 함께 소비할 수
있도록 BE 계약을 정의한다. FE 소비 이슈는 project_stock_frontend #146, 에픽 FE #152.

## Context

현재 FE가 "뉴스 및 공시 요약" 카드에 사용하는 계약은 `GET /api/v1/reports?asset_id=`
(research_reports)이다. 이 엔드포인트는 LLM이 생성한 종합 리포트를 반환하고,
내부에 `news_item_ids`(참조 뉴스 ID 배열)만 담겨 있어 항목별 메타데이터를 직접
제공하지 않는다. 뉴스는 `news_items` 테이블에 풍부한 컬럼이 이미 존재하지만
직접 노출하는 엔드포인트가 없고, 공시는 `app/adapters/disclosure/`에 mock 어댑터와
`DisclosureResult` 타입만 있으며 저장 테이블과 수집 잡이 존재하지 않는다.

## 기존 데이터 지형 (탐사 결과)

### news_items 테이블 (`app/domains/news/model.py`)

컬럼이 풍부하게 갖춰져 있다. 이번 계약에서 사용하는 컬럼은 다음과 같다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | int | PK |
| `asset_id` | int | FK → assets |
| `title` | str | 기사 제목 |
| `url` | str | 원문 링크 |
| `source` | str | 출처 |
| `published_at` | datetime \| None | 게시 시각 |
| `summary` | str \| None | AI 요약 (NewsAnalysisService가 채움) |
| `sentiment` | str \| None | `POSITIVE \| NEUTRAL \| NEGATIVE` |
| `impact_level` | str \| None | `LOW \| MEDIUM \| HIGH \| CRITICAL` |
| `trust_level` | str \| None | 신뢰도 레이블 (현재 미확정값) |
| `positive_factors` | str \| None | JSON 배열 직렬화 문자열 |
| `negative_factors` | str \| None | JSON 배열 직렬화 문자열 |

**없는 컬럼**: `category`(분류). 이번 이슈에서 신규 컬럼으로 추가한다.

### 공시 (disclosure)

`app/adapters/disclosure/base.py`의 `DisclosureResult`에는 `symbol`, `title`, `url`,
`source`, `published_at`, `payload`만 있다. 저장 테이블, 마이그레이션, 수집 잡이
존재하지 않는다. 이번 설계에서는 공시 축의 계약과 mock 파생까지만 정의하고,
실수집 파이프라인은 후속 이슈로 분리한다.

### 기존 엔드포인트

- `GET /api/v1/reports` — ResearchReport 목록. news 항목별 조회 불가.
- 뉴스 항목을 직접 반환하는 공개 엔드포인트는 현재 존재하지 않는다.
  (`POST /api/v1/worker/jobs/news`는 수집 트리거 전용이다.)

## 엔드포인트 결정

**신규 경로 `GET /api/v1/assets/{asset_id}/news-disclosure`를 추가한다.**

기존 `GET /api/v1/reports`를 확장하지 않는 이유는 두 가지다. 첫째, reports는
LLM 종합 리포트 단위이고 news-disclosure는 원자적 항목 배열이어서 도메인 경계가
다르다. 둘째, reports에 뉴스 항목 배열을 포함시키면 응답이 커지고 보안 경계
(`news_item_ids` 역참조)가 복잡해진다.

경로를 `assets/{asset_id}` 하위에 두는 것은 watchlists나 research-summary와 동일한
자산 중심 계층 구조를 따른 것이다(가정 — 에픽 #152에서 다른 경로를 결정했다면
Open Questions로 처리).

## Models

### 신규 컬럼 — `news_items` 테이블

`category` 컬럼을 추가하고 Alembic 마이그레이션을 생성한다.

| 컬럼 | 타입 | 제약 | 비고 |
|------|------|------|------|
| `category` | `String(30)` | nullable | 분류 enum 값 저장 |

`NewsItem` 모델에 `category: Mapped[str | None] = mapped_column(String(30), nullable=True)`를
추가한다.

### 신규 테이블 — 없음

공시를 저장하는 `disclosure_items` 테이블은 이번 이슈 범위 밖이다.
이번 설계에서 공시 응답은 `MockDisclosureProvider`가 반환하는 `DisclosureResult`를
직접 투영해 제공한다.

## Category 값 설계

`category` 필드의 enum 값과 파생 규칙을 정의한다. 값은 뉴스와 공시가 공유한다.

| 값 | 의미 |
|----|------|
| `EARNINGS` | 실적·매출·이익 관련 |
| `PRODUCT` | 신제품·서비스 출시 |
| `PARTNERSHIP` | 파트너십·협력 계약 |
| `REGULATION` | 규제·법률·소송·정부 조치 |
| `PERSONNEL` | 임원·경영진 변동 |
| `CAPITAL` | 증자·자사주·배당·자금 조달 |
| `MARKET` | 시황·산업 동향·경쟁사 |
| `OTHER` | 분류 불가 |

**파생 규칙**: `NewsAnalysisService.summarize()`가 AI 요약 시 `category`도 함께
결정하도록 확장한다. 구체적으로 `NewsSummaryResult`에 `category` 필드를 추가하고,
`update_summary()`가 이를 `news_items.category`에 저장한다. AI 요약이 아직 실행되지
않은 기사는 `category = None`(optional)으로 두고 FE는 null 허용으로 소비한다.

공시는 `DisclosureResult.payload`에서 category를 파생하는 로직을 `DisclosureService`에
구현하고, 실데이터가 없는 mock 단계에서는 `OTHER`로 고정한다(가정).

## Response Projections

### `NewsItemProjection`

`news_items` 컬럼 → 응답 필드 매핑이다.

| 응답 필드 | 소스 컬럼 | 타입 | Optional |
|-----------|-----------|------|----------|
| `id` | `news_items.id` | `int` | No |
| `title` | `news_items.title` | `str` | No |
| `url` | `news_items.url` | `str` | No |
| `source` | `news_items.source` | `str` | No |
| `published_at` | `news_items.published_at` | `UtcDatetime \| None` | Yes |
| `summary` | `news_items.summary` | `str \| None` | Yes |
| `category` | `news_items.category` | `str \| None` | Yes |
| `impact_level` | `news_items.impact_level` | `str \| None` | Yes |
| `sentiment` | `news_items.sentiment` | `str \| None` | Yes |

`trust_level`, `positive_factors`, `negative_factors`, `content_hash`,
`raw_news_event_id`는 이번 계약에 포함하지 않는다. FE가 필요로 하지 않고 응답 크기를
줄이기 위함이다.

### `DisclosureItemProjection`

`DisclosureResult` → 응답 필드 매핑이다.

| 응답 필드 | 소스 필드 | 타입 | Optional |
|-----------|-----------|------|----------|
| `title` | `DisclosureResult.title` | `str` | No |
| `url` | `DisclosureResult.url` | `str` | No |
| `source` | `DisclosureResult.source` | `str` | No |
| `published_at` | `DisclosureResult.published_at` | `datetime \| None` | Yes |
| `category` | `payload` 파생 또는 `OTHER` 고정 | `str \| None` | Yes |
| `impact_level` | 미구현 → `None` | `str \| None` | Yes |
| `summary` | 미구현 → `None` | `str \| None` | Yes |

### `NewsDisclosureResponse` (최상위 응답)

```
{
  "asset_id": int,
  "news": list[NewsItemProjection],
  "disclosures": list[DisclosureItemProjection]
}
```

## API

**파일**: `app/api/v1/endpoints/assets.py` (기존 라우터에 추가) 또는
신규 `app/api/v1/endpoints/news_disclosure.py`

| 항목 | 값 |
|------|----|
| HTTP 메서드 | GET |
| 경로 | `/api/v1/assets/{asset_id}/news-disclosure` |
| 쿼리 파라미터 | `limit: int = 20` (뉴스 항목 수, 공시는 어댑터 기본) |
| 응답 스키마 | `ApiResponse[NewsDisclosureResponse]` |
| 인증 | `get_current_user` (기존 패턴 동일) |

## Services

### `NewsDisclosureService` — `app/domains/news/news_disclosure_service.py`

```
def get_news_and_disclosures(
    self,
    asset_id: int,
    symbol: str,
    limit: int = 20,
) -> NewsDisclosureResponse
```
책임: news_items를 조회하고 DisclosureProvider를 호출해 두 배열을 조립해 반환한다.

### `NewsAnalysisService.summarize()` 확장

```
def summarize(self, news_item_id: int) -> NewsSummaryResult
```
책임: 기존 책임에 더해 `NewsSummaryResult.category`를 결정하고
`update_summary()`에 전달한다 (시그니처 변경 없음, 내부 확장).

## Repositories

### `NewsItemRepository` 확장 — `app/domains/news/repository.py`

기존 메서드에 추가한다.

```
def list_by_asset_with_limit(
    self,
    asset_id: int,
    limit: int = 20,
) -> list[NewsItem]
```
책임: `published_at DESC` 정렬로 최근 뉴스를 limit 건 반환한다.

```
def update_category(self, news_item_id: int, category: str) -> None
```
책임: `update_summary()`가 category까지 함께 저장하도록 분리하거나
`update_summary()`에 합산할 수 있다 — 구현 시 결정(Open Question 아님).

## Schema 변경

### `app/domains/news/schema.py`

- `NewsSummaryResult`에 `category: str | None = None` 추가.
- `NewsItemCreate`에 `category: str | None = Field(default=None, max_length=30)` 추가.
- 신규: `NewsItemProjection`, `DisclosureItemProjection`, `NewsDisclosureResponse`.

## Alembic Migration

`news_items` 테이블에 `category VARCHAR(30) NULL` 컬럼을 추가하는 마이그레이션을
생성한다. 기존 행은 NULL로 유지한다 (하위 호환).

## Dependencies

- `app/domains/news/` — NewsItem 모델, NewsItemRepository
- `app/adapters/disclosure/` — DisclosureProvider, MockDisclosureProvider
- `app/domains/assets/` — asset 존재 검증 (asset_id → symbol 조회)
- `app/core/` — ApiResponse, AppException, UtcDatetime

## Out of Scope

- 공시 실수집 파이프라인 (`disclosure_items` 테이블, 수집 잡, 실 어댑터).
- FE 렌더링 (project_stock_frontend #146).
- research_reports 계약 변경.
- `trust_level` 컬럼의 정의 및 파생 (별도 이슈).
- 페이지네이션 (이번은 `limit` 쿼리 파라미터로 단순화).

## 확정 사항 (오케스트레이터 결정, 2026-07-11)

1. **경로 위치** — `GET /api/v1/assets/{asset_id}/news-disclosure`로 확정한다.
   에픽 FE #152는 경로 형식을 별도로 확정하지 않았고, 기존
   `research-summary`·`buy-checklist`와 같은 자산 중심 계층을 따르는 것이
   일관적이다.
2. **asset → symbol 조회** — 공통 헬퍼 없음. `ResearchSummaryService`와 동일
   패턴으로 `AssetRepository.get_by_id(asset_id)`를 사용해 존재 검증과 symbol
   확보를 겸한다 (미존재 시 404 `ASSET_NOT_FOUND`).
3. **공시 limit** — 뉴스와 동일한 `limit` 파라미터를 공시 배열에도 적용한다
   (`published_at DESC` 기준 상한). 실 어댑터 도입 시 재검토한다.

## Open Questions

- 없음.
