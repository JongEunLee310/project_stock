# 032 Research Summary API

## Scope

LLM 또는 외부 집계 없이 종목 단위 리서치 요약 카드가 동작하도록 결정적 mock 요약을 제공한다.

## API

`GET /api/v1/assets/{asset_id}/research-summary`

- Auth: Required
- Response fields: `asset_id`, `positive_factors`, `negative_factors`, `items_to_verify`, `sources`, `updated_at`
- Missing asset: `404 ASSET_NOT_FOUND`

## Mock Strategy

서비스는 asset 존재를 먼저 검증한 뒤 asset id를 기반으로 고정 템플릿을 선택한다. 동일 입력은 동일 응답을 반환한다.

## Decisions

- DB table and migration are intentionally not added.
- Sources use lightweight `{type, label, url?}` objects so future news/disclosure/report aggregation can replace mock data without changing the main response shape.
