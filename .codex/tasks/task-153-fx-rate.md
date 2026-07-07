# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/228

## Task Summary

USD/KRW 환율을 제공하는 `GET /market/fx` 엔드포인트와 `ExchangeRateProvider` capability를 신설하고, 관심종목 확장 조회의 `AssetBriefResponse`에 `currency` 필드를 추가한다.

## Goal

- `GET /market/fx`가 envelope 형식으로 USD/KRW 환율(율·변동률·기준 시각)을 반환한다.
- 관심종목 확장 조회 응답의 asset에 `currency`가 포함된다.
- 검증 3종(ruff, mypy, pytest) 통과.

## Background

설계 문서: `docs/designs/228-fx-rate.md` — Verified Facts에 현재 코드 위치를 검증해 두었다. 구현 전 실코드와 대조하고 불일치하면 보고 후 실코드를 우선하라.

## Implementation Scope

설계 문서의 Interfaces 절을 따른다.

- `app/adapters/market/base.py` — `ExchangeRateResult` frozen dataclass, `ExchangeRateProvider` ABC
- `app/adapters/market/mock.py` — `MockExchangeRateProvider` (USD/KRW 포함 결정적 값, 미지원 페어 제외)
- `app/adapters/factory.py` — `get_exchange_rate_provider()` (mock 분기만, 그 외 NotImplementedError)
- `app/domains/market/schema.py` — `ExchangeRateResponse(pair, rate, change_percent, reference_at)`
- `app/domains/market/` 서비스 계층이 있으면 기존 구조를 따르고, 없으면 endpoints에서 provider를 직접 호출하는 기존 `/indices` 방식을 따른다
- `app/api/v1/endpoints/market.py` — `GET /fx?pairs=` (쉼표 구분, 기본 `USD/KRW`)
- `app/domains/watchlists/schema.py` — `AssetBriefResponse.currency: str | None = None` 추가
- `app/domains/watchlists/service.py` — `list_items_expanded`에서 quote 있으면 `quote.currency`, 없으면 None 전달
- 테스트: 설계 문서 Test Strategy 절의 4개 범주

## Out of Scope

- yfinance 환율 구현 (후속 이슈)
- FE 변경
- `AssetDetailResponse` 등 다른 응답의 통화 처리 변경

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- `pairs` 파라미터는 쉼표 구분 문자열로 받고, 공백을 정리한 뒤 대문자 정규화한다. 빈 값이면 기본 `USD/KRW`.
- mock 환율 값은 결정적이어야 한다 (매 호출 동일).
- 응답 envelope·에러 형식은 기존 market 엔드포인트와 동일하게 유지한다.
- `AssetBriefResponse` 변경은 필드 추가만으로 한다 (기존 필드·직렬화 형태 불변, FE 하위 호환).

## Test Requirements

- `MockExchangeRateProvider` 단위 테스트: USD/KRW 반환, 미지원 페어 제외, 결정성
- `GET /market/fx` 테스트: 기본 파라미터, 명시 파라미터, 미지원 페어만 요청 시 빈 목록
- 관심종목 확장 조회 currency 포함 테스트 (기존 테스트 보강, 약화 금지)
- factory 분기 테스트 (`tests/test_providers.py` 패턴)
- 기존 테스트를 약화하거나 삭제하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/228-fx-rate.md`의 Status를 구현 완료 후 `Implemented`로 갱신한다.

## ADR Need

불필요. 기존 provider 패턴의 capability 확장이다.

## Failure Record Need

불필요.

## Risk Level

Low — 신규 엔드포인트와 응답 필드 추가만 있고 기존 동작 변경이 없다.

## Expected Output

- 변경 파일 목록 보고
- 검증 3종 실행 결과 보고
- 설계 인용 위치의 실제 코드 일치 여부 보고
- 가정·잔여 위험 보고

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
- 현재 체크아웃된 브랜치(feat/228-fx-rate)에서 그대로 작업한다. 새 브랜치를 만들지 않는다. 커밋하지 않는다.
