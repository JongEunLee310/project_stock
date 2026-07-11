# Codex Handoff Task

## Source Issue

#268 — BE: 뉴스·공시 분리 및 메타데이터 계약 — 분류·중요도·영향·원문 링크
`gh issue view 268`

설계 문서: `docs/designs/268-news-disclosure-metadata.md` (반드시 먼저 읽는다.
"확정 사항" 절까지 포함해 그대로 따른다)

## Task Summary

`GET /api/v1/assets/{asset_id}/news-disclosure`를 신설해 뉴스(`news_items`)와
공시(mock `DisclosureProvider`)를 분리된 배열로 반환한다. `news_items`에
`category` 컬럼을 추가(Alembic)하고, `NewsAnalysisService.summarize()`가 AI
요약 시 category도 결정해 저장하도록 확장한다.

## Goal

작업 완료 시 다음 상태여야 한다.

- `GET /api/v1/assets/{asset_id}/news-disclosure?limit=20` (인증 필수)가
  `{ asset_id, news: NewsItemProjection[], disclosures:
  DisclosureItemProjection[] }`를 반환한다. 필드 구성은 설계 문서의
  Response Projections 표를 그대로 따른다.
- 자산 미존재 시 404 `ASSET_NOT_FOUND`. limit은 뉴스·공시 배열 모두에
  적용된다 (`published_at DESC`).
- `news_items.category`(String(30), nullable) 컬럼과 Alembic 마이그레이션이
  추가된다. 기존 행은 NULL 유지.
- `NewsSummaryResult`에 `category: str | None = None`가 추가되고,
  `summarize()`가 설계 문서의 category enum 8값
  (EARNINGS/PRODUCT/PARTNERSHIP/REGULATION/PERSONNEL/CAPITAL/MARKET/OTHER)
  중 하나를 결정해 `update_summary()` 경로로 저장한다. LLM 프롬프트
  (`app/adapters/llm/prompts/news_summary.py`)에 category 지시를 추가하되,
  파싱 실패·비정상 값은 None으로 폴백한다.
- 공시 mock 항목의 `category`는 `OTHER` 고정, `impact_level`·`summary`는
  None이다.
- `uv run ruff check .`, `uv run mypy .`,
  `NEWS_PROVIDER=mock uv run pytest`가 전부 통과한다.

## Background

- projection 네이밍 규칙: 경계 파생 뷰 타입은 'DTO'라 부르지 않고
  'Projection' 접미사를 쓴다 (ADR-009).
- `DisclosureProvider.fetch(symbols)`는 symbol 목록을 받는다. symbol은
  `AssetRepository.get_by_id(asset_id)`로 확보한다 (존재 검증 겸용,
  `ResearchSummaryService` 패턴).
- 로컬 `.env`의 `NEWS_PROVIDER=rss` 때문에 기본 pytest에서 worker 뉴스
  테스트 1건이 실패할 수 있다 — 검증은 `NEWS_PROVIDER=mock`으로 실행한다.

현재 브랜치 `feat/268-news-disclosure-metadata`에서 그대로 작업한다. 새
브랜치를 만들지 않는다.

## Implementation Scope

**신설**
- `app/domains/news/news_disclosure_service.py` — `NewsDisclosureService`
  (설계 문서 Services 절 시그니처).
- Alembic 마이그레이션 1개 (`news_items.category`).

**갱신**
- `app/domains/news/model.py` — `category` 컬럼.
- `app/domains/news/schema.py` — `NewsSummaryResult.category`,
  `NewsItemCreate.category`, 신규 projection 3종.
- `app/domains/news/repository.py` — `list_by_asset_with_limit`, category
  저장 경로.
- `app/domains/news/service.py` — `summarize()` category 확장.
- `app/adapters/llm/prompts/news_summary.py` — category 지시 추가.
- `app/api/v1/endpoints/assets.py` — 신규 GET 라우트.
- 테스트 — 아래 Test Requirements.

**변경 불가**
- `app/domains/reports/` (research_reports 계약 불변)
- `app/adapters/disclosure/base.py`의 `DisclosureResult` 형태
- 기존 news 수집 잡 동작

## Test Requirements

- 엔드포인트: 정상 응답 구조(news·disclosures 분리, 필드 구성), 404
  (자산 미존재), 401(미인증), limit 적용.
- summarize category: 정상 enum 값 저장, 비정상 값·파싱 실패 시 None 폴백.
- 마이그레이션 단일 head 유지.
- 픽스처는 실계약 형태 (news_items 컬럼·DisclosureResult 필드 그대로).

## Out of Scope

- 공시 실수집(테이블·잡·실 어댑터), FE, reports 계약 변경, trust_level,
  페이지네이션 meta.

## Rules

- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- 필요하지 않은 추상화를 추가하지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
