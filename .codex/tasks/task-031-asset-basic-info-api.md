# Codex Handoff Task

## Source Issue

Issue #51 (제목 Issue 31): `[BE] 종목 기본 정보 API 추가`

## Task Summary

종목 상세 페이지 상단 카드에 필요한 기본 정보(종목명/티커/시장/현재가/전일 대비/섹터·산업/설명/갱신시각)를 제공하는 API를 추가한다. 현재가·전일 대비는 Market Provider(mock)에서, 섹터/산업/설명은 Asset 모델 확장으로 제공한다.

## Goal

- `Asset`에 `sector`, `industry`, `description` 필드가 추가된다(모두 optional).
- 종목 상세 기본정보 API(`GET /api/v1/assets/{asset_id}/detail`)가 추가된다.
- 응답에 종목명/티커(symbol)/시장/현재가/전일종가/전일 대비(change, change_percent)/통화/섹터/산업/설명/`as_of`(갱신시각)가 포함된다.
- 시세는 `get_market_provider()`(mock)에서 결정적으로 제공되어 외부 API 키 없이 동작한다.
- 존재하지 않는 종목은 일관된 `404 ASSET_NOT_FOUND`를 반환한다.
- alembic 마이그레이션이 추가된다.

## Background

- 기존 모델: `app/domains/assets/model.py` — `Asset(symbol, name, market, is_active)`.
- 기존 조회: `GET /api/v1/assets/{asset_id}`는 `AssetResponse`를 반환(변경 금지, 하위호환). 상세 카드는 **신규** `/detail` 엔드포인트로 분리.
- 시세 어댑터: `app/adapters/factory.py::get_market_provider()` → `MockMarketDataProvider.get_quote(symbols)` → `QuoteResult(symbol,name,price,previous_close,change,change_percent,currency,as_of)`. 미등록 심볼도 결정적 fallback 시세를 반환.
- 응답 envelope: `app/core/response.py` `success`. 단건이므로 `meta` 없음.
- DB는 alembic(`alembic/versions/`). 컬럼 추가 시 마이그레이션 필수.
- 본 태스크는 #54(포트폴리오 섹터별 비중)의 선행 — `Asset.sector`가 거기서 재사용된다.

## Implementation Scope

- `app/domains/assets/model.py` — `Asset`에 `sector: str | None`, `industry: str | None`, `description: str | None`(Text/String, nullable) 추가.
- `app/domains/assets/schema.py` — `AssetDetailResponse`(기본정보 + 시세 합성). 기존 `AssetResponse`는 불변.
- `app/domains/assets/service.py` — `get_detail(asset_id)`: 종목 조회(없으면 `ASSET_NOT_FOUND`) 후 `get_market_provider().get_quote([symbol])` 합성.
- `app/api/v1/endpoints/assets.py` — `GET /{asset_id}/detail`(인증 불필요, 기존 `/assets` 정책과 동일) 추가. OpenAPI summary/description.
- `alembic/versions/` — 신규 마이그레이션(컬럼 추가).
- `docs/designs/031-asset-basic-info-api.md` — 스켈레톤 설계문서.

## Out of Scope

- 실데이터(real) market provider 구현 — mock만.
- 기존 `GET /assets/{asset_id}`·`POST /assets`·`GET /assets` 동작 변경(섹터/산업/설명은 생성 API에 optional로만 추가 가능, 필수화 금지).
- 차트/과거 시세/재무 등 상세 카드 외 데이터.

## Protected Files

변경하지 않는다:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

- 시세 호출은 반드시 factory(`get_market_provider()`) 경유 — provider 직접 인스턴스화 금지.
- `as_of`는 `QuoteResult.as_of`를 그대로 노출(갱신시각).
- 시세 합성 시 `Decimal`은 JSON 직렬화 정책상 문자열로 노출(기존 portfolio summary 예시와 동일 컨벤션).
- 존재하지 않는 `asset_id` → `404 ASSET_NOT_FOUND`(기존 메시지 재사용).
- 신규 모델 컬럼은 additive, 마이그레이션 upgrade/downgrade 작성.

## Test Requirements

- `/detail`이 등록 종목에 대해 기본정보 + mock 시세를 합성해 반환하는 테스트.
- mock provider가 미등록 심볼에도 결정적 fallback을 주는지(404 아님) 확인.
- 존재하지 않는 asset_id → `404 ASSET_NOT_FOUND`.
- `uv run pytest` 전체 통과.

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
```

## Documentation Impact

- `docs/designs/031-asset-basic-info-api.md` 신규(스켈레톤).
- `docs/api/frontend-api-spec.md` 종목상세 섹션에 `/detail` 추가(라우트 체크리스트 포함).

## ADR Need

없음 — 기존 어댑터 경계와 도메인 확장 범위.

## Failure Record Need

없음.

## Risk Level

Low~Medium — 마이그레이션 동반, 응답은 additive 신규 엔드포인트.

## Expected Output

- 모델/스키마/서비스/엔드포인트 + 마이그레이션 + 테스트.
- `uv run pytest`/lint/typecheck 통과.
- PR body에 `Closes #51`.

## Rules

- 시세는 factory 경유. provider 직접 생성 금지.
- 기존 엔드포인트 동작 불변.
- 보호 파일 변경 금지.
- 가정과 검증 결과 보고.
