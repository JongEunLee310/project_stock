# Codex Handoff Task

## Source Issue

https://github.com/JongEunLee310/project_stock/issues/226

## Task Summary

실시장 데이터 기반 종목 lookup API(`GET /assets/lookup`)를 신설하고, `POST /assets`를 서버 검증·보강 방식(symbol·market만 수신, name·sector는 provider에서 채움)으로 변경한다.

## Goal

- `GET /assets/lookup?query=AA&market=NASDAQ`이 심볼·종목명 부분 일치(대소문자 무시)로 실존 종목 목록과 `registered` 플래그를 반환한다.
- `POST /assets`가 `{symbol, market}`만 받고, 실존하지 않는 심볼은 422로 거부하며, 등록되는 행의 name·sector는 provider 데이터로 채워진다.
- 검증 3종(ruff, mypy, pytest) 통과.

## Background

설계 문서: `docs/designs/226-asset-lookup-validation.md` — Verified Facts에 현재 코드 위치·계약을 검증해 두었다. 구현 전 설계의 인용 위치가 실제 코드와 일치하는지 확인하고, 불일치하면 보고 후 실제 코드를 우선하라.

핵심 현황:

- provider 패턴: `app/adapters/market/base.py`의 capability별 ABC + frozen dataclass 결과, `app/adapters/factory.py`의 `settings.MARKET_PROVIDER` 분기 (mock/yfinance, 그 외 NotImplementedError)
- `app/domains/assets/service.py`의 `register`: 중복 검사(400 `ASSET_DUPLICATE`) 후 저장
- `yfinance>=1.5.1` 의존성 존재. codex 샌드박스는 네트워크가 차단되므로 yfinance 어댑터 테스트는 반드시 monkeypatch로 작성한다 (기존 `tests/test_price_ingestion.py`의 yfinance 테스트 패턴 참고).

## Implementation Scope

설계 문서의 Interfaces 절을 따른다.

- `app/adapters/market/base.py` — `SymbolLookupResult` dataclass, `SymbolLookupProvider` ABC 추가
- `app/adapters/market/mock.py` — `MockSymbolLookupProvider` (결정적 카탈로그 10여 개 종목, market·sector 포함, symbol·name 부분 일치·대소문자 무시, market 필터)
- `app/adapters/market/yfinance.py` — `YFinanceSymbolLookupProvider` (Yahoo Finance search 기반, sector 없으면 None, 네트워크 오류는 `MARKET_DATA_PROVIDER_ERROR` AppException으로 변환)
- `app/adapters/factory.py` — `get_symbol_lookup_provider()` (mock/yfinance 분기)
- `app/core/error_codes.py` — `ASSET_NOT_IN_MARKET` 추가
- `app/domains/assets/schema.py` — `AssetCreate`를 `symbol(≤20), market(≤20)` 2필드로 축소, `AssetLookupItem`/`AssetLookupResponse` 추가
- `app/domains/assets/service.py` — `register` 변경: symbol 대문자 정규화 → 중복 검사(기존 400 유지) → lookup provider 정확 심볼 일치 검증 → 미실존 422 `ASSET_NOT_IN_MARKET` → provider name·sector로 저장. lookup 서비스 메서드 추가(registered 플래그 조합).
- `app/api/v1/endpoints/assets.py` — `GET /lookup` 라우트 추가. 반드시 `/{asset_id}` 라우트보다 먼저 선언한다 (`lookup` 문자열이 int 파싱 422로 빠지는 것 방지).
- 기존 테스트 갱신: `tests/test_assets.py`의 POST 호출 2곳을 새 계약에 맞춘다 (mock 카탈로그에 있는 심볼 사용). 단언을 약화하지 않는다.
- 신규 테스트: 설계 문서 Test Strategy 절의 5개 범주.

## Out of Scope

- FE 변경 (project_stock_frontend#112에서 별도 진행)
- `GET /assets?symbol=` 완전 일치 필터 변경 (유지)
- assets 테이블 스키마·마이그레이션 변경 (industry/description 컬럼 유지, 등록 시 null)
- dev DB 오염 데이터 정리 (오케스트레이터가 별도 수행)

## Protected Files

없음. 보호 파일을 수정하지 않는다.

## Requirements

- lookup의 query는 1자 이상 필수 (빈 query는 422 VALIDATION_ERROR), market은 선택.
- registered 판정은 `AssetRepository.get_by_symbol_market` (symbol·market 쌍) 기준.
- 등록 시 provider 응답에서 요청 market과 일치하는 항목만 인정한다.
- mock 카탈로그에는 최소 AAPL, MSFT, GOOGL, AMZN, NVDA, TSLA를 포함하고 name·sector를 실제와 유사한 값으로 채운다 (예: AAPL → "Apple Inc." / "Technology").
- 응답 envelope·에러 형식은 기존 assets 엔드포인트와 동일하게 유지한다.
- yfinance 어댑터에서 Yahoo search 결과의 exchange를 market 표기(NASDAQ/NYSE 등)로 매핑하는 로직이 필요하면 명시적 매핑 테이블로 작성하고, 매핑 불가 항목은 결과에서 제외한다.

## Test Requirements

- `MockSymbolLookupProvider` 단위 테스트: 부분 일치, 대소문자 무시, market 필터, 무결과.
- lookup 엔드포인트 테스트: 등록된 종목의 `registered: true` / 미등록 `false`, 빈 query 422.
- `POST /assets` 테스트: 실존 심볼 등록 성공 + name·sector가 provider 값으로 저장됨, 미실존 심볼 422 `ASSET_NOT_IN_MARKET`, 중복 400 `ASSET_DUPLICATE` 유지, 소문자 입력 시 대문자 정규화.
- `YFinanceSymbolLookupProvider` 테스트: monkeypatch 기반 (네트워크 호출 금지), 정상 매핑·오류 변환.
- factory 분기 테스트 (`tests/test_providers.py` 패턴).
- 기존 테스트를 약화하거나 삭제하지 않는다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

`docs/designs/226-asset-lookup-validation.md`의 Status를 구현 완료 후 `Implemented`로 갱신한다. README·API 문서 갱신 대상 아님.

## ADR Need

불필요. 기존 provider 패턴의 capability 확장이며 새 아키텍처 결정이 없다.

## Failure Record Need

불필요.

## Risk Level

Medium — `POST /assets` 계약이 breaking으로 바뀌지만 유일 클라이언트(FE)는 후속 이슈에서 대응하며, 기존 테스트 영향 범위는 `tests/test_assets.py` 2곳으로 확인되었다.

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
- 현재 체크아웃된 브랜치(feat/226-asset-lookup-validation)에서 그대로 작업한다. 새 브랜치를 만들지 않는다. 커밋하지 않는다.
