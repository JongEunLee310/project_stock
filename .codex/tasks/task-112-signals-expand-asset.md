# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#112 — [계약정렬] signals 목록 expand=asset 지원 (G9 후속)

## Task Summary

`GET /api/v1/signals` 목록에 `?expand=asset`를 추가해, 지정 시 각 항목에 종목 brief(asset)를
합쳐 응답한다. watchlist `?expand=asset`(BE#99/PR#106)의 패턴을 그대로 이식한다.

## Goal

- `GET /api/v1/signals?asset_id=...&expand=asset` 호출 시 각 항목에
  `asset: { symbol, name, price, change_percent, sector? }`가 포함된다.
- `expand` 미지정/지원 외 값이면 기존 `SignalResponse` 응답 그대로(하위호환, `asset` 키 없음).
- 기존 `POST /signals`, `GET /signals/{id}` 동작 불변.

## Background

- **정본 계약**: `docs/designs/signals-expand-asset.md` §3. 충돌 시 이 문서가 우선.
- **참조 구현(반드시 일치시킬 패턴)**:
  - 라우터 expand 파싱·분기: `app/api/v1/endpoints/watchlists.py`의 `list_watchlist_items`.
  - 서비스 조인 로직: `app/domains/watchlists/service.py`의 `list_items_expanded`.
  - brief 스키마: `app/domains/watchlists/schema.py`의 `AssetBriefResponse`,
    `WatchlistItemExpandedResponse`.
- 와이어 컨벤션: snake_case, 금액=Decimal **문자열**(C5), 시각=`UtcDatetime`,
  공통 엔벨로프 `app/core/response.py`의 `paginated`.
- `AssetBriefResponse`는 새로 만들지 말고 `app.domains.watchlists.schema`에서 **import해 재사용**한다.
  (중복 정의·assets 모듈 승격 금지 — 범위 밖)

## Implementation Scope

- `app/domains/signals/schema.py`: `SignalExpandedResponse` 추가
  (`SignalResponse` 전 필드 + `asset: AssetBriefResponse | None = None`).
  `is_expired` 파생·`evidence` 파싱 등 기존 동작 보존(상속 또는 동일 검증자 재사용).
- `app/domains/signals/service.py`: `list_signals_expanded(...)` 추가.
  watchlist `list_items_expanded` 미러 — asset_id 모아 `AssetRepository.get_by_id`,
  존재 symbol들로 `get_market_provider().get_quote(symbols)` **1회 호출**, 항목별 합성.
  asset 미존재 시 `asset=None`, quote 미존재 시 `price`/`change_percent`는 `"0"`.
- `app/api/v1/endpoints/signals.py`: `list_signals`에 `expand: str | None = Query(...)` 추가.
  `"asset" in [e.strip() for e in expand.split(",")]`이면 expanded 경로, 아니면 기존 경로.
  `response_model`은 watchlist처럼 `ApiResponse[list[Any]]`로 완화하고 반환은 `Any`.
- `docs/api/frontend-api-spec.md`: signals 섹션에 `expand` 쿼리·확장 응답 설명 추가
  (watchlist expand 설명 형식과 동일하게).

## Out of Scope

- 마이그레이션/모델 변경(스키마 변경 없음).
- `AssetBriefResponse` 중복 정의 또는 assets 모듈로의 승격.
- signals 정렬/필터/다중 expand 확장.
- FE 어댑터.

## Protected Files

없음. `docs/designs/signals-expand-asset.md`·`.codex/*`·`docs/decisions/*`는 수정 금지(읽기 전용 참조).

## Requirements

- `expand=asset` 동작·응답 형태가 watchlist expand와 일관.
- 하위호환: 미지정 시 기존 응답 바이트 동일(추가 키 없음).
- get_quote는 항목 수와 무관하게 페이지당 1회 호출(N+1 금지).
- ruff/mypy 통과(타입 명시).

## Test Requirements

- `tests/test_signals.py`(없으면 신설 또는 기존 테스트 파일): 
  - `expand=asset` 시 항목에 `asset.symbol` 등 포함, `price`/`change_percent`가 문자열.
  - expand 미지정 시 `asset` 키 부재(하위호환).
  - asset 미존재 항목은 `asset` 가 null.
- `tests/test_api_contract.py`: signals expand 계약 케이스 추가(watchlist 계약 테스트 형식 참조).

## Verification Commands

```
uv run ruff check .
uv run mypy app
TZ=UTC uv run pytest
```

## Documentation Impact

`docs/api/frontend-api-spec.md` signals 섹션 갱신(범위 내). `contract-alignment.md` G9 상태 갱신은
머지 후 Opus가 후속 처리(수정 금지).

## ADR Need

불요. 기존 `?expand=asset` 패턴(watchlist) 재사용, 신규 아키텍처 결정 없음.

## Failure Record Need

불요.

## Risk Level

Low — 스키마/마이그레이션·인증 변경 없음, 검증된 패턴 이식, 하위호환 유지.

## Expected Output

- 위 4개 파일 + 테스트 변경.
- `uv run ruff check .` / `uv run mypy app` / `TZ=UTC uv run pytest` 전부 통과.
- 변경 요약 + 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
