# Codex Handoff Task

## Source Issue

BE #159(AssetBriefResponse에 market 노출). 설계 `docs/designs/asset-brief-market.md`.
FE #90(시그널 스파크라인)·FE #95(리서치 가격 라인차트)의 "심볼→market 매핑" 블로커를
unblock하기 위한 BE 선행 계약 확장이다.

## Task Summary

공유 계약 객체 `AssetBriefResponse`(`app/domains/watchlists/schema.py`)에 `market: str`
필드를 추가하고, 이 객체를 구성하는 3개 도메인 서비스(signals·watchlists·
alert_candidates)의 생성부에서 `market=asset.market`를 전달한다. asset 모델은 이미 market
컬럼을 보유하므로 스키마 마이그레이션은 없다.

## Goal

완료 시 참이어야 할 것:

- `AssetBriefResponse`가 `market: str` 필드를 노출한다.
- `?expand=asset`을 쓰는 signals·watchlists·alert_candidates 응답의 `asset` 객체에
  `market`이 해당 asset의 market 값으로 포함된다.
- 계약 테스트(`ASSET_BRIEF_CONTRACT`)와 세 도메인의 expand 테스트가 market을 확인한다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- `AssetBriefResponse`는 watchlist에서 정의되어 signals·watchlists·alert_candidates가
  **단일 정의로 공유**하는 계약 객체다(`docs/designs/signals-expand-asset.md`). 세 도메인이
  각각 `import`해 사용하므로, 필드 추가는 세 응답에 동시에 반영된다.
- `assets` 모델(`app/domains/assets/model.py`)은 이미 `market: Mapped[str]` 컬럼을 가진다
  (`symbol+market` unique 제약). asset 상세(`app/domains/assets/schema.py`)도 이미 market을
  노출한다. 따라서 이 작업은 마이그레이션 없이 기존 컬럼을 brief에 노출하는 것뿐이다.
- 세 서비스의 `AssetBriefResponse(...)` 생성부는 모두 `asset` 객체가 스코프에 있고
  `asset.symbol`·`asset.name`·`asset.sector`를 이미 전달한다. `asset.market`도 동일하게
  접근 가능하다(추가 조회·조인 불요).
  - `app/domains/signals/service.py`(생성부 약 76행)
  - `app/domains/watchlists/service.py`(생성부 약 143행)
  - `app/domains/alert_candidates/service.py`(생성부 약 109행)
- 와이어 컨벤션: snake_case. market은 문자열(`KRX|NASDAQ|NYSE` 등)이다.

## Implementation Scope

- `app/domains/watchlists/schema.py` — `AssetBriefResponse`에 `market: str` 추가. 필수
  필드로 두고 `symbol` 인접에 배치한다.
- `app/domains/signals/service.py` — `AssetBriefResponse(...)` 생성부에 `market=asset.market` 추가.
- `app/domains/watchlists/service.py` — 동일하게 `market=asset.market` 추가.
- `app/domains/alert_candidates/service.py` — 동일하게 `market=asset.market` 추가.
- `tests/test_api_contract.py` — `ASSET_BRIEF_CONTRACT`에 `"market": str` 추가.
- `tests/test_signals.py`·`tests/test_watchlist_expand.py`·`tests/test_alert_candidates.py`
  — asset brief 검증에 `market` 확인 추가(아래 Test Requirements).

## Out of Scope

- 스키마 마이그레이션(asset 모델은 이미 market 보유).
- 가격 시계열 엔드포인트(`app/api/v1/endpoints/prices.py`)·provider 변경.
- FE 변경(별도 repo, 본 PR 머지 후 FE #90에서 진행).
- `price`·`change_percent`·`sector` 등 기존 brief 필드 동작 변경.
- `AssetBriefResponse`를 assets 도메인으로 승격하는 리팩터(불필요한 변경).

## Protected Files

없음. 위 Implementation Scope 밖 파일은 변경하지 않는다.

## Requirements

- `market`을 필수 필드로 추가한다(세 생성부 모두 asset.market 접근 보장).
- 기존 brief 필드·동작을 변경하지 않는다(additive 확장).
- 공유 단일 정의를 유지한다(도메인별 중복 정의 금지).

## Test Requirements

- `tests/test_api_contract.py`: `ASSET_BRIEF_CONTRACT`에 `"market": str` 추가(계약 스키마
  키 집합 일치 검증 통과).
- `tests/test_signals.py`·`tests/test_alert_candidates.py`: asset brief 검증 루프에서
  `brief["market"]`이 fixture asset의 market 값과 일치함을 단언.
- `tests/test_watchlist_expand.py`: brief에 `"market"` 키 존재 및 값 일치 단언.
- 기존 단언(symbol·name·price·change_percent·sector)은 불변 유지.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/asset-brief-market.md`가 근거(브랜치에 포함됨). `docs/api/contract-alignment.md`
및 `docs/designs/signals-expand-asset.md`의 AssetBriefResponse 필드 기술 갱신은
orchestrator가 리뷰 시 판단한다(핵심 계약 변경 반영).

## ADR Need

불필요. 기존 컬럼을 공유 계약 응답에 노출하는 additive 확장으로, 신규 아키텍처 결정이 없다.

## Failure Record Need

불필요.

## Risk Level

Low. 마이그레이션 없는 additive 계약 확장이며, 세 생성부 모두 asset 객체가 이미 스코프에
있다. 주의점은 세 도메인이 공유 정의를 쓰므로 세 곳 생성부·세 테스트를 함께 갱신해야
한다는 점이다.

## Expected Output

- 위 scope의 스키마·서비스·테스트 변경.
- 검증 3종(ruff·mypy·pytest) 통과 로그.
- 가정(공유 정의 세 도메인 동시 반영·market 필수)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files or existing brief field behavior.
- Report assumptions and verification results.

## Stop Conditions

- 세 서비스 생성부 중 asset 객체가 스코프에 없어 `asset.market` 접근이 불가한 곳이 있으면
  멈추고 보고한다.
- asset 모델에 market 컬럼이 없거나 nullable이라 필수 필드 가정이 깨지면 멈추고 보고한다.
