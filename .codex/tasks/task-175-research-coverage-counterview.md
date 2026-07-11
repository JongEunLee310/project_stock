# Codex Handoff Task

## Source Issue

#271 — BE: 벤치마크 비교 시계열·데이터 신선도·분석 커버리지·반대 관점 계약 (2차)
`gh issue view 271 --repo JongEunLee310/project_stock`

설계 문서: `docs/designs/271-research-coverage-counterview.md` (반드시 먼저
읽는다). 벤치마크 비교 시계열은 이 작업 범위가 아니다 (후속 분리).

## Task Summary

리서치 상세 2차용 계약 두 가지를 구현한다.

1. `GET /assets/{asset_id}/research-coverage` — 데이터 축별 확보 상태·마지막
   수집 시각·건수. 기존 수집 데이터(news_items, stock_price_bars)에서
   **실제로 파생**한다 (mock 아님).
2. `ResearchSummaryResponse.counter_view` — 현재 stance에 반대되는 근거
   불릿 (결정적 mock 템플릿 확장).

## Goal

작업 완료 시 다음 상태여야 한다.

- `GET /assets/{asset_id}/research-coverage`가 항상 5개 축(NEWS, PRICE,
  EARNINGS, VALUATION, DISCLOSURE — 이 순서)을 반환한다.
  - NEWS: `news_items`에서 `asset_id` 일치 행 기준 —
    `status=COLLECTED`(행 존재 시), `last_collected_at=max(created_at)`,
    `item_count`.
  - PRICE: `stock_price_bars`에서 asset의 `symbol`+`market` 일치 행 기준
    — 동일 파생.
  - EARNINGS / VALUATION / DISCLOSURE: 항상 `NOT_COLLECTED`·null·0.
  - 인증 필수(401), 자산 미존재 404 `ASSET_NOT_FOUND` (기존 라우트 패턴).
- research-summary 응답에 `counter_view: list[str]`가 추가되고, 템플릿마다
  해당 stance에 반대되는 점검 유도형 한국어 불릿 2~3개가 들어간다. 같은
  asset_id 반복 호출은 동일 응답(결정성). 기존 필드는 불변.
- `uv run ruff check .`, `uv run mypy .`, `NEWS_PROVIDER=mock uv run
  pytest`가 전부 통과한다.

## Background

- 신규 도메인 구조는 `app/domains/catalysts/`(#269, PR #274)를 선례로
  따른다: schema.py + service.py, 라우트는
  `app/api/v1/endpoints/assets.py`에 추가, `AssetRepository.get_by_id`로
  존재 검증.
- counter_view는 `app/domains/research_summary/service.py`의
  `_SUMMARY_TEMPLATES` 로테이션(`asset.id % N`)에 필드를 추가하는
  방식이다 (#267 선례).
- `UtcDatetime`은 `app.core.schema`에 있다.

현재 브랜치 `feat/271-research-context-contract`에서 그대로 작업한다. 새
브랜치를 만들지 않는다.

## Implementation Scope

**신규**

- `app/domains/research_coverage/__init__.py`
- `app/domains/research_coverage/schema.py` — `CoverageAxis`,
  `ResearchCoverageResponse`
- `app/domains/research_coverage/service.py` — `ResearchCoverageService.
  get_coverage(asset_id)`
- `tests/test_research_coverage.py`

**갱신**

- `app/api/v1/endpoints/assets.py` — 라우트 1개 추가
- `app/domains/research_summary/schema.py` — `counter_view` 필드
  (`Field(default_factory=list)`)
- `app/domains/research_summary/service.py` — 템플릿에 counter_view 추가
- `tests/test_assets.py` — counter_view 검증. 계약 스냅샷 테스트가 있으면
  `tests/test_api_contract.py`도 갱신.

**변경 불가**

- alembic (신규 테이블·컬럼 없음), 다른 도메인, 수집 파이프라인,
  `app/adapters/`.

## Test Requirements

- research-coverage: 뉴스·가격 픽스처가 있는 자산 → NEWS·PRICE
  `COLLECTED` + last_collected_at·item_count 검증. 픽스처 없는 자산 → 5축
  전부 `NOT_COLLECTED`·null·0. 축 5개·순서 고정. 404·401.
- counter_view: 불릿 비어 있지 않음, 반복 호출 결정성, 기존 필드 회귀
  없음.
- 응답의 id 값을 리터럴로 단언하지 않는다 (StaticPool autoincrement 순서
  의존 금지 — PR #273 B1 선례).

## Out of Scope

- 벤치마크 비교 시계열, 공시·실적·밸류에이션 실수집, FE 변경.

## Rules

- 커밋은 1개로 만든다. push는 하지 않는다.
- 커밋 메시지는 한국어 `type: 본문` 형식으로 작성한다.
- 필요하지 않은 추상화를 추가하지 않는다.

## Verification

- `uv run ruff check .`
- `uv run mypy .`
- `NEWS_PROVIDER=mock uv run pytest`
